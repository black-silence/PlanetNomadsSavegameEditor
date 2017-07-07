#!/usr/bin/python
# -*- coding: utf-8 -*-
from tkinter import *
from tkinter import ttk, filedialog, messagebox
from tkinter.scrolledtext import ScrolledText
from typing import Text
import shutil
import os
from PlanetNomads import Savegame
import platform

"""
TODO
"""


class GUI(Frame):
    current_file = None
    savegame = None
    locked_buttons = []

    def __init__(self, parent):
        Frame.__init__(self, parent)
        self.parent = parent
        parent.title("Planet Nomads Savegame Editor 1.0.0")

        # Toolbar
        gui_toolbar_frame = ttk.Frame(parent, padding="5 5 5 5")
        gui_toolbar_frame.pack(fill="both", expand=True)

        gui_load_file_button = ttk.Button(gui_toolbar_frame, text="Select file", command=self.select_file)
        gui_load_file_button.grid(row=0, column=0, sticky=(E, W))

        gui_backup_button = ttk.Button(gui_toolbar_frame, text="Create backup", command=self.create_backup)
        gui_backup_button.grid(row=0, column=1, sticky=(E, W))
        self.locked_buttons.append(gui_backup_button)
        self.gui_restore_button = ttk.Button(gui_toolbar_frame, text="Restore backup", command=self.restore_backup)
        self.gui_restore_button.grid(row=0, column=2, sticky=(E, W))
        self.gui_restore_button.state(["disabled"])  # Restore button is unlocked separately

        # content
        gui_main_frame = ttk.Frame(parent, padding="5 5 5 5")
        gui_main_frame.grid_rowconfigure(0, weight=1)
        gui_main_frame.grid_columnconfigure(0, weight=1)
        gui_main_frame.pack(fill="both", expand=True)

        gui_tabs = ttk.Notebook(gui_main_frame)
        gui_tabs.grid(sticky=(N, E, S, W))

        gui_tabs.add(self.init_basic_buttons(gui_main_frame), text="Basic tools")
        gui_tabs.add(self.init_machine_buttons(gui_main_frame), text="Machine tools")
        gui_tabs.add(self.init_cheat_buttons(gui_main_frame), text="Cheats")
        gui_tabs.add(self.init_dev_buttons(gui_main_frame), text="Dev tools")

        # status
        gui_status_frame = ttk.Frame(parent, relief="sunken", padding="2 2 2 2")
        gui_status_frame.pack(fill="both", expand=True)
        self.gui_status = ScrolledText(gui_status_frame, state='disabled', width=40, height=5, wrap='none')
        self.gui_status.pack(expand=True, fill="both")

        for button in self.locked_buttons:
            button.state(["disabled"])

    def init_machine_buttons(self, gui_main_frame):
        frame = ttk.Frame(gui_main_frame)

        options = ["Select machine"]
        self.gui_selected_machine_identifier = StringVar(self.parent)
        self.gui_selected_machine_identifier.set(options[0])

        self.gui_machine_select = ttk.OptionMenu(frame, self.gui_selected_machine_identifier, *options)
        self.gui_machine_select.grid(sticky=(E, W))
        self.locked_buttons.append(self.gui_machine_select)

        gui_push_machine_button = ttk.Button(frame, text="Push selected machine up by 20 meters",
                                             command=self.push_machine_up)
        gui_push_machine_button.grid(sticky=(E, W))
        self.locked_buttons.append(gui_push_machine_button)

        return frame

    def update_machine_select(self, machines):
        menu = self.gui_machine_select["menu"]
        menu.delete(0, "end")
        menu.add_command(label="Select machine")

        for m in machines:
            menu.add_command(label="{} {}".format(m.get_type(), m.get_name_or_id()),
                             command=lambda value=m.identifier: self.gui_selected_machine_identifier.set(value))
        self.gui_selected_machine_identifier.set("Select machine")

    def init_dev_buttons(self, gui_main_frame):
        gui_dev_tools_frame = ttk.Frame(gui_main_frame)

        gui_inventory_button = ttk.Button(gui_dev_tools_frame, text="List player inventory",
                                          command=self.list_inventory)
        gui_inventory_button.grid(sticky=(E, W))
        self.locked_buttons.append(gui_inventory_button)

        gui_machines_button = ttk.Button(gui_dev_tools_frame, text="List machines", command=self.list_machines)
        gui_machines_button.grid(sticky=(E, W))
        self.locked_buttons.append(gui_machines_button)

        gui_teleport_northpole_button = ttk.Button(gui_dev_tools_frame,
                                                   text="Teleport player to north pole (death possible)",
                                                   command=self.teleport_northpole)
        gui_teleport_northpole_button.grid(sticky=(E, W))
        self.locked_buttons.append(gui_teleport_northpole_button)
        return gui_dev_tools_frame

    def init_basic_buttons(self, gui_main_frame):
        gui_basic_tools_frame = ttk.Frame(gui_main_frame)

        gui_unlock_button = ttk.Button(gui_basic_tools_frame, text="Unlock all recipes", command=self.unlock_recipes)
        gui_unlock_button.grid(sticky=(E, W))
        self.locked_buttons.append(gui_unlock_button)

        gui_northbeacon_button = ttk.Button(gui_basic_tools_frame, text="Create north pole beacon",
                                            command=self.create_north_beacon)
        gui_northbeacon_button.grid(row=0, column=1, sticky=(E, W))
        self.locked_buttons.append(gui_northbeacon_button)

        gui_southbeacon_button = ttk.Button(gui_basic_tools_frame, text="Create GPS beacons",
                                            command=self.create_gps_beacons)
        gui_southbeacon_button.grid(row=1, column=1, sticky=(E, W))
        self.locked_buttons.append(gui_southbeacon_button)
        return gui_basic_tools_frame

    def push_machine_up(self):
        machine_id = self.gui_selected_machine_identifier.get()
        if machine_id == "Select machine":
            self.update_statustext("Select a machine first")
            return
        machine_id = int(machine_id)
        for machine in self.savegame.machines:
            if machine.identifier != machine_id:
                continue
            machine.push_up(20)
            self.update_statustext("Machine {} pushed".format(machine.get_name_or_id()))
            self.savegame.save()

    def init_cheat_buttons(self, gui_main_frame):
        gui_cheats_frame = ttk.Frame(gui_main_frame)
        gui_resource_menu = Menu(gui_cheats_frame, tearoff=0)
        gui_resource_menu.add_command(label="Aluminium", command=lambda: self.create_item(51))
        gui_resource_menu.add_command(label="Biomass Container", command=lambda: self.create_item(392745))
        gui_resource_menu.add_command(label="Carbon", command=lambda: self.create_item(49))
        gui_resource_menu.add_command(label="Cobalt", command=lambda: self.create_item(60))
        gui_resource_menu.add_command(label="Iron", command=lambda: self.create_item(56))
        gui_resource_menu.add_command(label="Silicium", command=lambda: self.create_item(52))
        gui_resource_menu.add_command(label="Silver", command=lambda: self.create_item(59))
        gui_resource_menu.add_command(label="Titanium", command=lambda: self.create_item(57))
        gui_resource_menubutton = ttk.Menubutton(gui_cheats_frame, text="Cheat: add resource", menu=gui_resource_menu)
        gui_resource_menubutton.grid(sticky=(E, W))
        self.locked_buttons.append(gui_resource_menubutton)

        gui_item_menu = Menu(gui_cheats_frame, tearoff=0)
        gui_item_menu.add_command(label="Composite 1", command=lambda: self.create_item(78))
        gui_item_menu.add_command(label="Mechanical 1", command=lambda: self.create_item(76))
        gui_item_menubutton = ttk.Menubutton(gui_cheats_frame, text="Cheat: add item", menu=gui_item_menu)
        gui_item_menubutton.grid(sticky=(E, W))
        self.locked_buttons.append(gui_item_menubutton)

        gui_unlock_button = ttk.Button(gui_cheats_frame, text="Cheat: give Mk4 equipment",
                                       command=self.create_mk4_equipment)
        gui_unlock_button.grid(sticky=(E, W))
        self.locked_buttons.append(gui_unlock_button)
        return gui_cheats_frame

    def teleport_northpole(self):
        if self.savegame.teleport_player(0, 16250, 0):
            self.update_statustext("Player teleported")

    def update_statustext(self, message: str):
        self.gui_status.config(state=NORMAL)
        self.gui_status.insert(END, message + "\n")
        self.gui_status.see(END)
        self.gui_status.config(state=DISABLED)

    def select_file(self):
        """
        Show file select dialog
        :return: None
        """
        opts = {"filetypes": [("PN save files", "save_*.db"), ("All files", ".*")]}
        os_name = platform.system()
        if os_name == "Linux":
            opts["initialdir"] = os.path.expanduser("~/.config/unity3d/Craneballs/PlanetNomads/")
        elif os_name == "Windows":
            opts["initialdir"] = os.path.expanduser("~\AppData\LocalLow\Craneballs\PlanetNomads")
        # TODO MAC > USERS > [Your Username] > Library > Application Support > unity.Craneballs.PlanetNomads

        filename = filedialog.askopenfilename(**opts)
        if not filename:
            return
        self.load_file(filename)

    def load_file(self, filename: Text):
        """
        Load file
        :type filename: Filename with absolute path
        """
        self.current_file = filename

        self.savegame = Savegame.Savegame()
        self.savegame.load(self.current_file)
        self.update_statustext("Loaded game '{}'".format(self.savegame.get_name()))

        # Enable some buttons once a file is loaded
        for button in self.locked_buttons:
            button.state(["!disabled"])

        if self.backup_exists(filename):
            self.gui_restore_button.state(["!disabled"])
        else:
            self.gui_restore_button.state(["disabled"])

        self.update_machine_select(self.savegame.machines)

    def backup_exists(self, filename: Text) -> bool:
        """
        Check if a backup exists for the given file
        :param filename: Filename with absolute path
        :return: bool
        """
        return os.path.exists(filename + ".bak")

    def create_backup(self):
        if self.backup_exists(self.current_file):
            if not messagebox.askokcancel("Overwrite existing backup?", "A backup already exists. Overwrite it?"):
                return
        try:
            shutil.copy2(self.current_file, self.current_file + ".bak")
        except IOError:
            messagebox.showerror(message="Could not create backup file!")
        else:
            messagebox.showinfo("Backup created", "Backup was created")
            self.gui_restore_button.state(["!disabled"])

    def restore_backup(self):
        res = messagebox.askokcancel("Please confirm", "Are you sure you want to restore the backup?")
        if not res:
            return
        try:
            shutil.copy2(self.current_file + ".bak", self.current_file)
            self.savegame.reset()
        except IOError:
            messagebox.showerror(message="Could not restore backup file!")
        else:
            messagebox.showinfo("Backup restore", "Backup was restored")

    def list_machines(self):
        for m in self.savegame.machines:
            print(m)

    def unlock_recipes(self):
        if self.savegame.unlock_recipes():
            self.update_statustext("All blocks unlocked")
        else:
            self.update_statustext("Nothing unlocked. Is this a survival save?")

    def create_north_beacon(self):
        self.savegame.create_north_pole_beacon()
        self.update_statustext("Beacon created with nav point C")

    def create_gps_beacons(self):
        self.savegame.create_gps_beacons()
        self.update_statustext("3 beacons created, north pole + 2x equator")

    def list_inventory(self):
        inventory = self.savegame.get_player_inventory()
        stacks = inventory.get_stacks()
        for slot in stacks:
            print("Slot {}: {} {}".format(slot, stacks[slot].get_count(), stacks[slot].get_item_name()))

    def create_item(self, item_id, amount=70):
        inventory = self.savegame.get_player_inventory()
        if not inventory:
            self.update_statustext("Could not load inventory")
            return
        item = Savegame.Item(item_id)

        if not inventory.add_stack(item, amount):
            messagebox.showerror(message="Could not create resource. All slots full?")
            return
        self.update_statustext("Added {} to inventory".format(item.get_name()))
        inventory.save()

    def create_mk4_equipment(self):
        self.create_item(118, 1)
        self.create_item(114, 1)
        self.create_item(110, 1)


if __name__ == "__main__":
    window = Tk()
    app = GUI(window)
    window.mainloop()
