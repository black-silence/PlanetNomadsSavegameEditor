#!/usr/bin/python
# -*- coding: utf-8 -*-
import sqlite3
import xml.etree.ElementTree as ETree
import re
import random
import zipfile
import os
import atexit
from math import sqrt
from collections import OrderedDict


class Savegame:
    def __init__(self):
        self.filename = ""
        self.temp_extracted_file = ""
        self.loaded = False
        self.dbconnector = None
        self.db = None
        self.__machines = []
        self.settings = None
        atexit.register(self.cleanup)

    def __del__(self):
        self.cleanup()

    def cleanup(self):
        if self.db:
            self.db.close()
            self.db = None
        os.remove(self.temp_extracted_file)

    def load(self, filename):
        self.filename = filename
        with zipfile.ZipFile(filename, "r") as myzip:
            self.temp_extracted_file = myzip.extract("_working.db", "PNSE_extract")
        self.dbconnector = sqlite3.connect(self.temp_extracted_file)
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
        self.on_save()
        return True

    def get_player_position(self):
        self.db.execute("select value from simple_storage where key = 'playerData'")
        player_data = self.db.fetchone()["value"]
        lines = player_data.split("\n")
        for key, line in enumerate(lines):
            if line.startswith("PL"):
                continue
            return [float(x) for x in line.split(" ")[:3]]
        raise IOError("Player data not found in simple_storage")

    def get_setting(self, name):
        if not self.settings:
            self.db.execute("select value from simple_storage where key='advanced_settings'")
            try:
                self.settings = ETree.fromstring(self.db.fetchone()["value"])
            except TypeError:
                # Old games don't have advanced settings in simple storage
                return None
        for tag in self.settings:
            if tag.tag == name:
                return tag.text
        return None

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

    def on_save(self):
        self.dbconnector.commit()
        self.write_zip()

    def save(self):
        for m in self.__machines:
            if not m.is_changed():
                continue
            data = '<?xml version="1.0" encoding="utf-8"?>' + m.get_xml_string()
            update = (data, m.transform, m.identifier)
            self.db.execute("update machine set data = ?, transform = ? where id = ?", update)
            # write changed active blocks too, required for pushing stuff around
            active_blocks = m.get_changed_active_blocks()
            for b in active_blocks:
                update = (active_blocks[b].get_xml_string(), b)
                self.db.execute("update active_blocks set data = ? where id = ?", update)
        self.on_save()

    def write_zip(self):
        #  PN uses deflate so to be safe this is the mode we want to use
        with zipfile.ZipFile(self.filename, "w", zipfile.ZIP_DEFLATED) as myzip:
            myzip.write(os.path.join("PNSE_extract", "_working.db"), "_working.db")

    def unlock_recipes(self):
        unlock_string = "PL1\n" + "_".join([str(i) for i in range(1, 100)])
        self.db.execute("update simple_storage set value = ? where key = 'playerTechnology'", (unlock_string,))
        affected = self.db.rowcount
        self.on_save()
        return affected > 0

    def debug(self):
        print("Debug info")
        print('Name: {}'.format(self.get_name()))
        print("Number of machines: {}".format(len(self.machines)))

    def get_planet_size(self):
        radius = self.get_setting("PlanetRadius")
        if radius:
            return int(radius)
        # Old games had 10k, even older games may have 16k. Not important enough to calculate it.
        return 10000

    def get_player_inventory(self):
        inventory = Container(self.db, self.on_save)
        if not inventory.load(0):
            return
        return inventory

    def create_north_pole_beacon(self):
        """Create a solar beacon with navigation C on at the north pole."""
        self.create_beacon(0, self.get_planet_size(), 0)

    def create_south_pole_beacon(self):
        """Create a solar beacon with navigation C on at the south pole."""
        self.create_beacon(0, -1 * self.get_planet_size(), 0, rot_z=-180)

    def create_gps_beacons(self):
        self.create_beacon(0, self.get_planet_size(), 0)  # North pole
        self.create_beacon(self.get_planet_size(), 0, 0, rot_z=90)
        self.create_beacon(0, 0, self.get_planet_size(), rot_z=90)

    def create_beacon(self, x, y, z, rot_x=0, rot_y=0, rot_z=0):
        self.db.execute("select max(id) as mx from active_blocks")
        next_active_id = int(self.db.fetchone()["mx"]) + 1

        xml = '<ActiveBlock xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" ' \
              'xmlns:xsd="http://www.w3.org/2001/XMLSchema" ID="{}" Type_ID="56" Container_ID="-1" Name="">' \
              '<Module ID="0" Type="SwitchModule"><Prop key="TurnState"><value xsi:type="xsd:int">1</value></Prop></Module>' \
              '<Module ID="1" Type="PowerIn" />' \
              '<Module ID="2" Type="PositionModule"><Prop key="BasePosition"><value xsi:type="xsd:string">{:0.0f};{:0.0f};{:0.0f}</value></Prop></Module>' \
              '<Module ID="3" Type="PowerOut"><Prop key="PowerState"><value xsi:type="xsd:int">0</value></Prop></Module>' \
              '<Module ID="4" Type="SwitchModule"><Prop key="TurnState"><value xsi:type="xsd:int">0</value></Prop></Module>' \
              '<Module ID="5" Type="SensorModule" />' \
              '<Module ID="6" Type="RenameModule" />' \
              '<Module ID="7" Type="ConnectPowerInOutModule" />' \
              '<Module ID="8" Type="NavigationModule"><Prop key="Icon"><value xsi:type="xsd:int">2</value></Prop><Prop key="TurnState"><value xsi:type="xsd:int">1</value></Prop></Module>' \
              '</ActiveBlock>'.format(next_active_id, x, y, z)

        sql = "INSERT INTO active_blocks (id, type_id, data, container_id) VALUES (?, 56, ?, -1)"
        self.db.execute(sql, (next_active_id, xml))

        sql = 'INSERT INTO machine (id, data, transform) VALUES (?, ?, ' \
              '"{:0.0f} {:0.0f} {:0.0f} {:0.0f} {:0.0f} {:0.0f}")'.format(x, y, z, rot_x, rot_y, rot_z)
        machine_id = random.Random().randint(1000000, 10000000)  # Is there a system behind the ID?
        xml = '<?xml version="1.0" encoding="utf-8"?>\n' \
              '<MachineSaveData xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema">\n' \
              '<Grid ID="{}">\n' \
              '<BasePosition X="{:0.0f}" Y="{:0.0f}" Z="{:0.0f}" />' \
              '<BaseRotation X="{:0.0f}" Y="{:0.0f}" Z="{:0.0f}" />' \
              '<Blocks>\n' \
              '<Block ID="56" Health="80" Weld="80" Ground="true" ActiveID="{}">' \
              '<Pos x="0" y="0" z="0" /><Rot v="0" /><Col r="0" g="0" b="0" />' \
              '</Block>\n' \
              '</Blocks>\n</Grid>\n</MachineSaveData>\n'.format(machine_id, x, y, z, rot_x, rot_y, rot_z, next_active_id)
        self.db.execute(sql, (machine_id, xml))

        # Solar beacon is self powered
        sql = 'INSERT INTO activeblocks_connector_power (block_id_1, module_id_1, block_id_2, module_id_2, power) ' \
              'VALUES (?, 3, ?, 1, 20)'
        self.db.execute(sql, (next_active_id, next_active_id))

        # No idea what this does
        sql = 'INSERT INTO machine_rtree_rowid (rowid, nodeno) VALUES (?, 1)'
        self.db.execute(sql, (machine_id,))

        # Insert into machine_rtree seems unhealthy

        self.on_save()


class Container:
    """0-based, player inventory = index 0
    contents is 0-based, serialized json-like
    first item is probably a version
    v:1,0:{package:com.planetnomads, id:59, count:1, props:},1:{...},
    """
    stacks = {}
    size = 0
    db_key = None

    def __init__(self, db, save_callback):
        self.db = db
        self.save_callback = save_callback

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
        self.save_callback()
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
        80: "Fabric Mk1",
        81: "Fabric Mk2",
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
        self.type = None

        root = ETree.fromstring(self.xml)
        for node in root:
            if node.tag == "Grid":
                self.grid.append(Grid(node))
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
            self.active_block_data[row["id"]] = ActiveBlock(row["data"])

    def randomize_color(self):
        for g in self.grids:
            g.randomize_color()
        self.changed = True

    def set_color(self, color, replace=None):
        for g in self.grids:
            g.set_color(color, replace)
        self.changed = True

    def get_xml_string(self):
        """Save the current machine, replaces original xml"""
        xml = ETree.Element("MachineSaveData")
        for g in self.grid:
            g.build_xml(xml)
        return ETree.tostring(xml, "unicode")

    def is_changed(self):
        return self.changed

    def get_changed_active_blocks(self):
        result = {}
        for aid in self.active_block_data:
            active_block = self.active_block_data[aid]
            if active_block.changed:
                result[aid] = active_block
        return result

    def __str__(self):
        grounded = self.is_grounded()
        return "Machine {} ({})".format(
            self.get_name_or_id(),
            self.get_type()
        )

    def is_grounded(self):
        for g in self.grids:  # TODO only 1 grid per machine now
            if g.is_grounded():
                return True
        return False

    def teleport(self, distance: int, target):
        """Teleport machine over/under the target."""
        rot_x, rot_y, rot_z = self.get_rotation()
        (x, y, z) = self.get_coordinates()

        (target_x, target_y, target_z) = target.get_coordinates()
        distance_to_planet_center = sqrt(target_x ** 2 + target_y ** 2 + target_z ** 2)
        factor = 1 + distance / distance_to_planet_center
        target_x2 = target_x * factor  # TODO use np
        target_y2 = target_y * factor
        target_z2 = target_z * factor

        self.transform = "{:0.3f} {:0.3f} {:0.3f} {} {} {}".format(target_x2, target_y2, target_z2, rot_x, rot_y, rot_z)
        # Use the exact difference to move subgrids, this is important or the object will disappear
        difference = (target_x2 - x, target_y2 - y, target_z2 - z)
        for g in self.grid:
            g.move_by(difference, self.active_block_data)
        self.changed = True

    def get_rotation(self):
        """Get rotation as tuple of string"""
        (x, y, z, rotX, rotY, rotZ) = [x for x in self.transform.split(" ")]
        return rotX, rotY, rotZ

    def get_coordinates(self):
        """Get coords as tuple of x, y, z"""
        (x, y, z, rotX, rotY, rotZ) = [x for x in self.transform.split(" ")]
        return [float(i) for i in (x, y, z)]

    def get_name_or_id(self):
        n = self.get_name()
        if n:
            return n
        return self.identifier

    def get_type(self):
        if self.type:
            return self.type
        self.type = "Construct"
        if not self.is_grounded():
            if self.has_cockpit():
                self.type = "Vehicle"
                return "Vehicle"
            # If it has no cockpit it's random scattered blocks
            return "Construct"
        if self.has_generator():
            self.type = "Base"
            return "Base"
        return "Construct"

    def get_name(self):
        if self.name is not None:
            return self.name
        for g in self.grids:
            name = g.get_name(self.active_block_data)
            if name:
                self.name = name
                return name
        self.name = ""
        return ""

    def has_cockpit(self):
        return self.grids[0].has_cockpit()

    def has_generator(self):
        return self.grids[0].has_generator()


class XmlNode:
    """Basic XML node"""
    def __init__(self, node):
        self.type = node.tag
        self._attribs = OrderedDict()
        self._children = []
        for a in node.attrib:
            self._attribs[a] = node.attrib[a]
        expected_children = self.get_expected_children_types()
        for item in node:
            if item.tag in expected_children:
                self._children.append(globals()[item.tag](item))  # Create object from class name
            else:
                print("Unexpected children type %s" % item.tag)

    def get_attribs(self):
        """Get attributes in the original order, much easier to diff xml this way"""
        return self._attribs

    def get_children(self):
        return self._children

    def build_xml(self, xml):
        sub = ETree.SubElement(xml, self.type, self.get_attribs())
        for c in self._children:
            c.build_xml(sub)

    def get_expected_children_types(self):
        return []


class MachineNode(XmlNode):
    def get_active_block_ids(self):
        res = []
        for c in self._children:
            try:
                res.extend(c.get_active_block_ids())
            except AttributeError:
                pass  # Class doesn't have active blocks
        return res

    def is_grounded(self):
        for c in self.get_children():
            try:
                if c.is_grounded():
                    return True
            except AttributeError:
                pass
        return False

    def has_cockpit(self):
        for x in self.get_children():
            try:
                if x.has_cockpit():
                    return True
            except AttributeError:
                pass
        return False

    def has_generator(self):
        for c in self.get_children():
            try:
                if c.has_generator():
                    return True
            except AttributeError:
                pass
        return False

    def has_hoverjack(self):
        for c in self.get_children():
            try:
                if c.has_hoverjack():
                    return True
            except AttributeError:
                pass
        return False

    def get_name(self, active_block_data):
        for c in self.get_children():
            try:
                name = c.get_name(active_block_data)
                if name != "":
                    return name
            except AttributeError:
                pass
        return ""

    def get_expected_children_types(self):
        return ['Grid']

    def move_by(self, vector, active_block_data):
        for c in self._children:
            try:
                c.move_by(vector, active_block_data)
            except AttributeError:
                pass

    def randomize_color(self):
        for c in self._children:
            try:
                c.randomize_color()
            except AttributeError:
                pass

    def set_color(self, color, replace):
        for c in self._children:
            try:
                c.set_color(color, replace)
            except AttributeError:
                pass


class Blocks(MachineNode):
    def get_expected_children_types(self):
        return ['Block']


class BasePosition(XmlNode):
    def move_by(self, vector, active_blocks):
        x = float(self._attribs["X"])
        y = float(self._attribs["Y"])
        z = float(self._attribs["Z"])
        self._attribs["X"] = "{:0.5f}".format(x + vector[0])
        self._attribs["Y"] = "{:0.5f}".format(y + vector[1])
        self._attribs["Z"] = "{:0.5f}".format(z + vector[2])


class BaseRotation(XmlNode):
    pass


class BaseBounds(XmlNode):
    def move_by(self, vector, active_blocks):
        x = float(self._attribs["MinX"])
        y = float(self._attribs["MinY"])
        z = float(self._attribs["MinZ"])
        self._attribs["MinX"] = "{:0.5f}".format(x + vector[0])
        self._attribs["MinY"] = "{:0.5f}".format(y + vector[1])
        self._attribs["MinZ"] = "{:0.5f}".format(z + vector[2])
        x = float(self._attribs["MaxX"])
        y = float(self._attribs["MaxY"])
        z = float(self._attribs["MaxZ"])
        self._attribs["MaxX"] = "{:0.5f}".format(x + vector[0])
        self._attribs["MaxY"] = "{:0.5f}".format(y + vector[1])
        self._attribs["MaxZ"] = "{:0.5f}".format(z + vector[2])


class DistancePhysicsFreezeData(XmlNode):
    pass


class Pos(XmlNode):
    pass


class Rot(XmlNode):
    pass


class Col(XmlNode):
    def randomize_color(self):
        self._attribs["r"] = str(random.randrange(0, 255))
        self._attribs["g"] = str(random.randrange(0, 255))
        self._attribs["b"] = str(random.randrange(0, 255))

    def set_color(self, color, replace):
        if replace:
            if int(self._attribs["r"]) != replace[0]:
                return
            if int(self._attribs["g"]) != replace[1]:
                return
            if int(self._attribs["b"]) != replace[2]:
                return
        self._attribs["r"] = str(int(color[0]))
        self._attribs["g"] = str(int(color[1]))
        self._attribs["b"] = str(int(color[2]))


class Grid(MachineNode):
    """Every machine has 1 Grid which contains 1 Blocks"""
    def get_expected_children_types(self):
        return ['Blocks', 'BasePosition', 'BaseRotation', 'BaseBounds', 'DistancePhysicsFreezeData']


class SubGrid(Grid):
    pass


class ActiveBlock:
    def __init__(self, xml):
        self.root = ETree.fromstring(xml)
        self.name = self.root.attrib.get("Name", "")
        self.changed = False

    def get_xml_string(self):
        return ETree.tostring(self.root, "unicode")

    def get_name(self):
        return self.name

    def move_by(self, vector):
        for node in self.root:
            if node.tag != "Module":
                continue
            if node.attrib["Type"] != "PositionModule":
                continue
            position = node[0][0].text
            x, y, z = [float(i) for i in position.split(";")]
            node[0][0].text = "{:0.3f};{:0.3f};{:0.3f}".format(x + vector[0], y + vector[1], z + vector[2])
            self.changed = True


class Block(MachineNode):
    types = {
        1: "Full Armor Block",
        2: "Corner Armor Block",
        3: "Compact Battery Rack",
        4: "Cockpit 2x3",
        5: "Reinforced Wall",
        6: "Armor Corner Slope - Inverted",
        7: "Armor Corner Slope - Long Inverted",
        8: "Armor Corner Slope",
        9: "Armor Slope Long",
        10: "Armor Slope Corner (Long)",
        11: "Armor Slope",
        #12 active
        13: "Conveyor L-Section",
        14: "Conveyor",
        15: "Conveyor T-Section",
        16: "Conveyor X-Section",
        #17 probly active block
        18: "Wheel",
        19: "Compact Container",
        20: "Bio Generator",
        21: "Reinforced Wall with Light",
        22: "Reinforced Wall - Short",
        23: "Reinforced Wall Corner",
        24: "Reinforced Wall Outer Corner",
        25: "Base Foundation (double height)",
        26: "Raised Floor",
        #27
        28: "Compact Medbay",
        29: "Medium Refinery",
        #30
        #31
        32: "Reinforced Wall with Door",
        33: "Ceiling Panel",
        34: "Suspension",
        #35 probly active
        36: "Jack tool",
        37: "Hover Jack",
        38: "Railing",
        39: "Short Railing",
        40: "Stairs",
        41: "Beacon",
        42: "Uranium Generator",
        43: "Ceiling Light",
        44: "Indoor Light",
        45: "Search Light - Front Mount",
        46: "Search Light - Top Mount",
        47: "Large Container",
        48: "Fence",
        49: "Fence Corner",
        50: "Ramp",
        51: "Inner Wall with Doors",
        52: "Reinforced Wall Exterior/Interior Joint",
        53: "Short inner wall",
        54: "Inner Wall",
        55: "Windowed Outer Wall",
        56: "Solar Beacon",
        57: "Escape pod",

        61: "Base Foundation",

        64: "Emergency 3D printer",

        66: "Hinge",
        68: "Rotating Plate",
        71: "Item Dispenser",
        73: "Mining Machine",
        76: "Medium Armory",
        78: "Medium Medbay",
        79: "Escape Pod (broken)",  # 3k health
        80: "Radar",  # 300 health
        81: "Winch",
        82: "Winch Shackle",
        83: "Thruster",  # 300 health
        84: "Tank",  # 250 health
        85: "Big Tank",  # 750 health
        86: "Sloped Arc Corner",
        87: "Corner Arc",
        88: "Arc Block",
        #89
        90: "Wreck Container",
        91: "Wreck Beacon",
        92: "Cockpit 3x3",
        93: "Rounded Cockpit 2x3",
        94: "Buggy Wheel",
        95: "Mobile Base Wheel",
        96: "Large Suspension",
        97: "Rounded Cockpit 3x3",
        98: "Switchboard",
        100: "Hover Pad",
        101: "Floating Foundation",
        114: "Air Blade",
        126: "Glassed Cockpit 3x3",
    }

    def is_grounded(self):
        return "Ground" in self._attribs and self._attribs["Ground"] == "true"

    def get_active_block_id(self):
        if "ActiveID" in self._attribs:
            return int(self._attribs["ActiveID"])
        return None

    def get_active_block_ids(self):
        result = []
        active_id = self.get_active_block_id()
        if active_id:
            result.append(active_id)
        result.extend(super(Block, self).get_active_block_ids())
        return result

    def get_active_block(self, active_blocks):
        aid = self.get_active_block_id()
        if aid:
            if aid == 0:
                pass
            elif aid in active_blocks:
                return active_blocks[aid]
            else:
                # Avoid crash if active block did not load. Why is it missing though?
                print("Active block %i not found" % aid)
        return None

    def get_name(self, active_blocks):
        active_block = self.get_active_block(active_blocks) # type: ActiveBlock
        if active_block:
            name = active_block.get_name()
            if name:
                return name
        return super().get_name(active_blocks)

    def has_cockpit(self):
        if self._attribs["ID"] in ("4", "92", "93", "97", "126"):
            return True
        return super().has_cockpit()

    def has_generator(self):
        if self._attribs["ID"] in ("20", "42"):
            return True
        return super().has_generator()

    def has_hoverjack(self):
        if self._attribs["ID"] == "37":
            return True
        return super().has_hoverjack()

    def get_expected_children_types(self):
        return ['Pos', 'Col', 'Rot', 'SubGrid']

    def move_by(self, vector, active_blocks):
        super().move_by(vector, active_blocks)
        active_block = self.get_active_block(active_blocks)
        if not active_block:
            return
        active_block.move_by(vector)
