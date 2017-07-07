#!/usr/bin/python
# -*- coding: utf-8 -*-
import sqlite3
import xml.etree.ElementTree as ETree
import re
import random
from math import sqrt
from collections import OrderedDict


class Savegame:
    def __init__(self):
        self.filename = ""
        self.loaded = False
        self.dbconnector = None
        self.db = None
        self.__machines = []

    def __del__(self):
        self.db.close()

    def load(self, filename):
        self.filename = filename
        self.dbconnector = sqlite3.connect(filename)
        self.db = self.dbconnector.cursor()
        self.db.row_factory = sqlite3.Row
        self.loaded = True
        self.reset()

    def reset(self):
        self.__machines = []

    def get_name(self):
        if not self.loaded:
            raise ValueError("No file loaded")
        self.db.execute("select value from simple_storage where key = 'game_name'")
        return self.db.fetchone()["value"]

    def teleport_player(self, x, y, z):
        self.db.execute("select value from simple_storage where key = 'playerData'")
        player_data = self.db.fetchone()["value"]
        lines = player_data.split("\n")
        for key, line in enumerate(lines):
            if line.startswith("PL"):
                continue
            current_position = line.split(" ")
            current_position[0] = "{:0.3f}".format(x)
            current_position[1] = "{:0.3f}".format(y)
            current_position[2] = "{:0.3f}".format(z)
            lines[key] = " ".join(current_position)
        player_data = "\n".join(lines)
        self.db.execute("update simple_storage set value = ? where key = 'playerData'", (player_data,))
        self.dbconnector.commit()
        return True

    @property
    def machines(self):
        if not self.__machines:
            self.__load_machines()
        return self.__machines

    def __load_machines(self):
        self.db.execute("select * from machine")
        for row in self.db.fetchall():
            self.__machines.append(Machine(row, self.db))
        self.db.execute("select * from active_blocks")
        active_block_data = self.db.fetchall()
        for m in self.__machines:
            m.set_active_blocks(active_block_data)

    def save(self):
        for m in self.__machines:
            if not m.is_changed():
                continue
            data = '<?xml version="1.0" encoding="utf-8"?>' + m.get_xml_string()
            insert = (data, m.transform, m.identifier)
            self.db.execute("update machine set data = ?, transform = ? where id = ?", insert)
        self.dbconnector.commit()

    def unlock_recipes(self):
        unlock_string = "PL1\n" + "_".join([str(i) for i in range(1, 100)])
        self.db.execute("update simple_storage set value = ? where key = 'playerTechnology'", (unlock_string,))
        affected = self.db.rowcount
        self.dbconnector.commit()
        return affected > 0

    def debug(self):
        print("Debug info")
        print('Name: {}'.format(self.get_name()))
        print("Number of machines: {}".format(len(self.machines)))

    def get_player_inventory(self):
        inventory = Container(self.db, self.dbconnector)
        if not inventory.load(0):
            return
        return inventory

    def create_north_pole_beacon(self):
        """Create a solar beacon with navigation C on at the north pole."""
        self.create_beacon(0, 16000, 0)

    def create_south_pole_beacon(self):
        """Create a solar beacon with navigation C on at the south pole."""
        self.create_beacon(0, -16000, 0, rot_z=-180)

    def create_gps_beacons(self):
        self.create_beacon(0, 16000, 0)  # North pole
        self.create_beacon(16000, 0, 0, rot_z=90)
        self.create_beacon(0, 0, 16000, rot_z=90)

    def create_beacon(self, x, y, z, rot_x=0, rot_y=0, rot_z=0):
        xml = '<?xml version="1.0" encoding="utf-8"?>\n<Data blockName="">\n<Module id="0" TurnState="1" />\n' \
              '<Module id="1" />\n' \
              '<Module id="2" SavedBasePositionX="{:0.0f}" SavedBasePositionY="{:0.0f}" SavedBasePositionZ="{:0.0f}" />\n' \
              '<Module id="3" PowerState="0"/>\n<Module id="4" TurnState="0"/>\n<Module id="5"/>\n<Module id="6"/>\n' \
              '<Module id="7" />\n<Module id="8" Icon="2" TurnState="1" />\n</Data>\n'.format(x, y, z)
        sql = "INSERT INTO active_blocks (id, type_id, data, container_id) VALUES (NULL, 56, ?, -1)"
        self.db.execute(sql, (xml,))
        active_id = self.db.lastrowid

        sql = 'INSERT INTO machine (id, data, transform) VALUES (?, ?, ' \
              '"{:0.0f} {:0.0f} {:0.0f} {:0.0f} {:0.0f} {:0.0f}")'.format(x, y, z, rot_x, rot_y, rot_z)
        machine_id = random.Random().randint(1000000, 10000000)  # Is there a system behind the ID?
        xml = '<?xml version="1.0" encoding="utf-8"?>\n<Machine>\n' \
              '<Grid gridId="{}">\n' \
              '<Block ID="56" x="0" y="0" z="0" rotation="0" r="0" g="0" b="0" health="80" weld="80" grounded="True" ' \
              'activeId="{}" />\n' \
              '</Grid>\n</Machine>\n'.format(machine_id, active_id)
        self.db.execute(sql, (machine_id, xml))

        # Solar beacon is self powered
        sql = 'INSERT INTO activeblocks_connector_power (block_id_1, module_id_1, block_id_2, module_id_2, power) ' \
              'VALUES (?, 3, ?, 1, 20)'
        self.db.execute(sql, (active_id, active_id))

        # No idea what this does
        sql = 'INSERT INTO machine_rtree_rowid (rowid, nodeno) VALUES (?, 1)'
        self.db.execute(sql, (machine_id,))

        # Insert into machine_rtree seems unhealthy

        self.dbconnector.commit()


class Container:
    """0-based, player inventory = index 0
    contents is 0-based, serialized json-like
    first item is probably a version
    v:1,0:{package:com.planetnomads, id:59, count:1, props:},1:{...},
    """
    stacks = {}
    size = 0
    db_key = None

    def __init__(self, db, connector):
        self.db = db
        self.dbconnector = connector

    def load(self, key):
        """Load container from db
        :return bool
        """
        sql = "select * from containers where id = ?"
        self.db.execute(sql, (key,))
        row = self.db.fetchone()
        if not row:
            return False
        self.size = row["size"]
        self.stacks = ContentParser.parse_item_stack(row["content"])
        self.db_key = key
        return True

    def save(self):
        sorted_keys = sorted(self.stacks)
        s = []
        for key in sorted_keys:
            s.append("{}:{}".format(key, self.stacks[key].get_db_string()))
        sql = "update containers set content = ? where id = ?"
        self.db.execute(sql, ("v:1," + ",".join(s) + ",", self.db_key))
        self.dbconnector.commit()
        return True

    def get_stacks(self):
        return self.stacks

    def add_stack(self, item, count):
        if len(self.stacks) >= self.size:
            return False
        for i in range(self.size):
            stack = self.stacks.get(i, None)
            if stack:
                continue  # skip all stacks that are occupied
            self.stacks[i] = Stack(item, count=count)
            return True

    def __str__(self):
        return "Container with {} slots, {} slots used".format(self.size, len(self.stacks))


class ContentParser:
    """
    Content is 0-based, serialized json-like. The number shows the slot in the container, empty slots are skipped.
    ~0.6.8 added a version number as first item
    Example: v:1,0:{package:com.planetnomads, id:59, count:1, props:},10:{...},
    """

    @staticmethod
    def parse_item_stack(content):
        # TODO check version number
        start = content.find(",")
        content = content[start + 1:]  # Remove version number because it breaks my nice regexes
        regex_val = re.compile(r"[, {](\w+):([^,}]*)[,}]")
        regex_slot = re.compile(r"^(\d+):{")
        parts = re.split(r"(?<=}),(?=\d+:{|$)", content)
        result = {}
        for part in parts:
            if part == "":
                continue

            m = regex_slot.match(part)
            if m:
                key = int(m.group(1))
            else:
                continue

            vars = {}
            m = regex_val.findall(part)
            if m:
                for k, v in m:
                    if k == "id":
                        item_id = int(v)
                    elif k == "count":
                        vars[k] = int(v)
                    else:
                        vars[k] = v

            item = Item(item_id)
            stack = Stack(item, **vars)
            result[key] = stack

        return result


class Stack:
    def __init__(self, item, count=1, package="com.planetnomads", props="False", infinityCount="False"):
        self.item = item
        self.count = count
        self.package = package
        self.props = props
        self.infinity_count = infinityCount

    def get_item_name(self):
        return self.item.get_name()

    def get_count(self):
        return self.count

    def get_db_string(self):
        start = "{"
        end = "}"
        data = "package:{}, id:{}, count:{}, infinityCount:{}, props:{}".format(self.package, self.item.item_type,
                                                                                self.count, self.infinity_count,
                                                                                self.props)
        return start + data + end

    def __str__(self):
        return "Stack of {} {}".format(self.get_count(), self.item.get_name())


class Item:
    names = {
        33: "Battery",
        49: "Carbon",
        51: "Aluminium",
        52: "Silicium",
        56: "Iron",
        57: "Titanium",
        58: "Gold",
        59: "Silver",
        60: "Cobalt",
        61: "Uranium",
        62: "Xaenite",
        63: "Enriched Uranium",
        64: "Deuterium",
        65: "Xaenite Rod",
        67: "Plating",
        68: "Composite Plating",
        69: "Basic Frame",
        70: "Reinforced Frame",
        72: "Glass Components",
        73: "Standard Electronics",
        74: "SuperConductive Electronics",
        75: "Quantum Electronics",
        76: "Standard Mechanical Components",
        77: "SuperAlloy Mechanical",
        78: "Composite Parts",
        79: "Advanced Composite Parts",
        80: "Fabric",
        81: "Super Fabric",
        82: "ALM",
        83: "Advanced ALM",
        84: "Super ALM",
        86: "Fruitage",
        87: "Dirty Water",
        88: "Herbs",
        89: "Raw Meat",
        90: "Purified Water",
        91: "Electrolytes Water",
        92: "Nutrition Capsules",
        93: "Super Food",
        95: "Bandages",
        96: "Stimulation Injection",
        108: "Exploration Suit Mk2",
        109: "Exploration Suit Mk3",
        110: "Exploration Suit Mk4",
        112: "Jetpack Mk2",
        113: "Jetpack Mk3",
        114: "Jetpack Mk4",
        116: "MultiTool Mk2",
        117: "MultiTool Mk3",
        118: "MultiTool Mk4",
        392745: "Biomass Container",
        9550358: "Seeds",
        11691828: "Sleeping Bag",
    }

    def __init__(self, item_type: int):
        self.item_type = item_type

    def get_name(self):
        if self.item_type in self.names:
            return self.names[self.item_type]

        return "unknown item type {}".format(self.item_type)


class Machine:
    """
    0 16000 0 0 0 0 = north pole at sea level
    0 -16000 0 0 0 180 = south pole at sea level, "upside down"
    planet diameter is 32km
    """

    def __init__(self, db_data, db):
        self.identifier = db_data['id']
        self.xml = db_data['data']
        self.transform = db_data['transform']
        self.loaded = False
        self.grid = []  # Only one grid per machine
        self.changed = False
        self.active_block_ids = []
        self.db = db
        self.name = None

        root = ETree.fromstring(self.xml)
        for node in root:
            if node.tag == "Grid":
                self.grid.append(Grid(node, self))
            else:
                raise IOError("Unexpected element %s in machine" % node.tag)

        self.active_block_ids = self.grid[0].get_active_block_ids()
        self.active_block_data = {}

    @property
    def grids(self):
        return self.grid

    def set_active_blocks(self, data):
        for row in data:
            if row["id"] not in self.active_block_ids:
                continue
            self.active_block_data[row["id"]] = row

    def randomize_color(self):
        for g in self.grid:
            for b in g.blocks:
                b.randomize_color()
        self.changed = True

    def get_xml_string(self):
        """Save the current machine, replaces original xml"""
        xml = ETree.Element("Machine")
        for g in self.grid:
            g.build_xml(xml)
        return ETree.tostring(xml, "unicode")

    def is_changed(self):
        return self.changed

    def __str__(self):
        grounded = self.is_grounded()
        return "Machine {} ({})".format(
            self.get_name_or_id(),
            "Building" if grounded else "Vehicle"
        )

    def is_grounded(self):
        for g in self.grids:
            if g.is_grounded():
                return True
        return False

    def push_up(self, distance: int):
        """Push machine away from the planet center."""
        (x, y, z, rotX, rotY, rotZ) = [x for x in self.transform.split(" ")]
        (x, y, z) = [float(i) for i in (x, y, z)]
        distance_to_planet_center = sqrt(x ** 2 + y ** 2 + z ** 2)
        factor = 1 + distance / distance_to_planet_center
        x2 = x * factor
        y2 = y * factor
        z2 = z * factor
        self.transform = "{:0.3f} {:0.3f} {:0.3f} {} {} {}".format(x2, y2, z2, rotX, rotY, rotZ)
        # Use the exact difference to move subgrids
        # Looks like active_blocks does not have to be adjusted
        difference = (x2 - x, y2 - y, z2 - z)
        for g in self.grid:
            g.move_by(difference)
        self.changed = True

    def get_name_or_id(self):
        n = self.get_name()
        if n:
            return n
        return self.identifier

    def get_type(self):
        if self.is_grounded():
            return "Building"
        return "Vehicle"

    def get_name(self):
        if self.name is not None:
            return self.name
        for g in self.grids:
            name = g.get_name()
            if name:
                self.name = name
                return name
        self.name = ""
        return ""


class Structure:
    """Grids contain blocks. Blocks may contain grids. Structure is a logic base for both."""

    def __init__(self, node, machine):
        self._children = []
        self._attribs = OrderedDict()
        self.machine = machine
        for item in node:
            if item.tag == "Grid":
                self._children.append(Grid(item, machine))
            elif item.tag == "Block":
                self._children.append(Block(item, machine))
            else:
                raise IOError("Unexpected element %s in structure" % item.tag)
        # Make sure no attribute is lost from the original xml
        for a in node.attrib:
            self._attribs[a] = node.attrib[a]

    def get_attribs(self):
        """Get attributes in the original order, much easier to diff xml this way"""
        return self._attribs

    def move_by(self, vector):
        for c in self._children:
            c.move_by(vector)

    def get_active_block_ids(self):
        res = []
        for c in self._children:
            res.extend(c.get_active_block_ids())
        return res

    def build_xml(self, xml):
        pass

    def get_name(self):
        for c in self._children:
            name = c.get_name()
            if name:
                return name
        return ""


class Grid(Structure):
    @property
    def blocks(self):
        return self._children

    def build_xml(self, xml):
        sub = ETree.SubElement(xml, "Grid", self.get_attribs())
        for c in self._children:
            c.build_xml(sub)

    def is_grounded(self):
        for c in self._children:
            if c.is_grounded():
                return True
        return False

    def move_by(self, vector):
        if "position" in self._attribs:
            (x, y, z) = [float(i) for i in self._attribs["position"].split(" ")]
            self._attribs["position"] = "{:0.3f} {:0.3f} {:0.3f}".format(x + vector[0], y + vector[1], z + vector[2])
        super(Grid, self).move_by(vector)


class ActiveBlock:
    def __init__(self, xml):
        root = ETree.fromstring(xml)
        self.name = root.attrib.get("blockName", "")

    def get_name(self):
        return self.name


class Block(Structure):
    types = {
        1: "Full Armor Block",
        4: "Cockpit 2x3",
        14: "Conveyor",
        18: "Wheel",
        19: "Compact Container",
        26: "Raised Floor",
        32: "Reinforced Wall with Door",
        34: "Suspension",
        36: "Jack",
        42: "Uranium Generator",
        43: "Ceiling Light",
        53: "Short inner wall",
        56: "Solar Beacon",
        57: "Escape pod",
        61: "Base Foundation",
        64: "Emergency 3D printer",
        66: "Hinge",
        73: "Mining Machine",
    }

    def randomize_color(self):
        self._attribs["r"] = random.randrange(0, 255)
        self._attribs["g"] = random.randrange(0, 255)
        self._attribs["b"] = random.randrange(0, 255)

    def is_grounded(self):
        return "grounded" in self._attribs and self._attribs["grounded"] == "True"

    def get_active_block_ids(self):
        result = []
        if "activeId" in self._attribs:
            result.append(int(self._attribs["activeId"]))
        result.extend(super(Block, self).get_active_block_ids())
        return result

    def build_xml(self, xml):
        sub = ETree.SubElement(xml, "Block", self.get_attribs())
        for c in self._children:
            c.build_xml(sub)

    def get_name(self):
        if "activeId" in self._attribs:
            id = int(self._attribs["activeId"])
            active_block_data = self.machine.active_block_data[id]
            active_block = ActiveBlock(active_block_data["data"])
            name = active_block.get_name()
            if name:
                return name
        return super(Block, self).get_name()
