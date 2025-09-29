"""
Cute Portrait Trainer - Tkinter (simplified)
- Leave `game` and `module` as None (you will set them).
- Auto-checks process on startup and quits if not found.
- Uses ReadWriteMemory for writes, pymem for pointer reads.
- Portrait layout, simple look.
- Infinite fuel writes the float(100.00) bytes repeatedly to freeze.
- Boost recalibration supported.
- Save button lives in the Hotkeys window only.
"""

import os
import sys
import json
import time
import struct
import threading
import ctypes
from ctypes import wintypes
import tkinter as tk
from tkinter import messagebox, ttk

# images
try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except Exception:
    PIL_AVAILABLE = False

# memory libs
try:
    from ReadWriteMemory import ReadWriteMemory
    RWM_AVAILABLE = True
except Exception:
    RWM_AVAILABLE = False

try:
    import pymem
    import pymem.process
    PYMEM_AVAILABLE = True
except Exception:
    PYMEM_AVAILABLE = False

import psutil

# hotkey lib
try:
    import keyboard
    KEYBOARD_AVAILABLE = True
except Exception:
    KEYBOARD_AVAILABLE = False

# ---------------------------
# ToolTip class
# ---------------------------
class ToolTip(object):
    def __init__(self, widget, text='widget info'):
        self.widget = widget
        self.text = text
        self.tw = None
        self.widget.bind("<Enter>", self.enter)
        self.widget.bind("<Leave>", self.leave)

    def enter(self, event=None):
        x, y, _, _ = self.widget.bbox("insert")
        x += self.widget.winfo_rootx() + 25
        y += self.widget.winfo_rooty() + 20
        self.tw = tk.Toplevel(self.widget)
        self.tw.wm_overrideredirect(True)
        self.tw.wm_geometry("+%d+%d" % (x, y))
        label = tk.Label(self.tw, text=self.text, background='yellow', relief='solid', borderwidth=1, padx=1)
        label.pack(ipadx=1)

    def leave(self, event=None):
        if self.tw:
            self.tw.destroy()

# ---------------------------
# EXACT functions you asked to keep (unchanged)
# ---------------------------
def get_module_base_address(process_name, module_name):
    try:
        pm = pymem.Pymem(process_name)
        module = pymem.process.module_from_name(pm.process_handle, module_name)
        if module:
            return module.lpBaseOfDll
        else:
            return 0x0
    except:
        return 0x0

def get_base_address(process_name):
    try:
        pm = pymem.Pymem(f"{process_name}")
        return pymem.process.module_from_name(pm.process_handle, f"{process_name}").lpBaseOfDll
    except:
        return 0x0

# ---------------------------
# Set these before running (left as None for you to edit)
# ---------------------------
game = "HillClimbRacing.exe"         # e.g. "Hill Climb Racing.exe"  <-- set this in the file before running
module = "cocos2d-win10.dll"       # e.g. "game.dll"    <-- set if needed

# ---------------------------
# Offsets/constants from your original spec
# ---------------------------
COINS_OFFSET = 0x28CAD4
DIAMONDS_OFFSET = 0x28CAEC
FUEL_BASE_OFFSET = 0x0028CA2C
FUEL_OFFSETS = [0x2A8]
BOOST_BASE_OFFSET = 0x00396244
BOOST_OFFSETS = [0x4,0x14,0x14,0x8,0x30,0xF8,0xE4]
BOOST_SECONDARY_OFFSETS = [0x4,0x14,0x14,0x8,0x7C,0xF8,0xE4]
BOOST_THIRD_OFFSETS = [0x4,0x14,0x14,0x8,0x8C,0xF8,0xE4]

CONFIG_PATH = "config.json"

# ---------------------------
# Memory helper (compact)
# ---------------------------
class MemHelper:
    def __init__(self):
        self.rwm_proc = None
        self.pm = None
        self.pid = None
        self.backend = None

    def attach_by_name(self, proc_name):
        """Attach using process name; raises on failure."""
        pid = None
        for p in psutil.process_iter(['pid','name']):
            if p.info['name'] and p.info['name'].lower() == proc_name.lower():
                pid = p.info['pid']; break
        if not pid:
            raise ProcessLookupError(f"Process '{proc_name}' not found.")
        return self.attach_by_pid(pid)

    def attach_by_pid(self, pid):
        self.detach()
        self.pid = pid
        # try ReadWriteMemory for writes
        if RWM_AVAILABLE:
            try:
                rwm = ReadWriteMemory()
                proc = rwm.get_process_by_id(pid)
                proc.open()
                self.rwm_proc = proc
                self.backend = 'rwm'
            except Exception:
                self.rwm_proc = None
        # pymem for reads/pointer traversal
        if PYMEM_AVAILABLE:
            try:
                pm = pymem.Pymem()
                pm.open_process_from_id(pid)
                self.pm = pm
            except Exception:
                self.pm = None
        if not (self.rwm_proc or self.pm):
            raise RuntimeError("Could not attach to process (need ReadWriteMemory or pymem). Try running as Admin.")

    def detach(self):
        try:
            if self.rwm_proc:
                try: self.rwm_proc.close()
                except: pass
            if self.pm:
                try: self.pm.close_process()
                except: pass
        finally:
            self.rwm_proc = None
            self.pm = None
            self.pid = None
            self.backend = None

    # read helpers (pymem required)
    def read_int(self, addr):
        if not self.pm:
            raise RuntimeError("pymem not available")
        return self.pm.read_int(addr)

    def read_uint(self, addr):
        if not self.pm:
            raise RuntimeError("pymem not available")
        return self.pm.read_uint(addr)

    def read_float(self, addr):
        if not self.pm:
            raise RuntimeError("pymem not available")
        return self.pm.read_float(addr)

    # write helpers (prefer rwm, fallback to pymem)
    def write_bytes(self, addr, b: bytes):
        if self.rwm_proc:
            try:
                # many RWM bindings accept list of ints
                if hasattr(self.rwm_proc, 'writeBytes'):
                    self.rwm_proc.writeBytes(addr, list(b))
                    return
                if hasattr(self.rwm_proc, 'writeByte'):
                    for i, bb in enumerate(b):
                        self.rwm_proc.writeByte(addr + i, [bb])
                    return
            except Exception:
                # fallback to pymem
                pass
        if self.pm:
            self.pm.write_bytes(addr, b, len(b))
            return
        raise RuntimeError("No available write backend")

    def write_int(self, addr, value):
        b = int(value).to_bytes(4, byteorder='little', signed=True)
        self.write_bytes(addr, b)

    def write_uint(self, addr, value):
        b = int(value).to_bytes(4, byteorder='little', signed=False)
        self.write_bytes(addr, b)

    def write_float_bytes_as_int(self, addr, float_value):
        """Pack float into 4 bytes and write raw bytes (so float bits are placed; interpreted as float by game)."""
        b = struct.pack('<f', float(float_value))
        self.write_bytes(addr, b)

    # pointer resolver
    def resolve_pointer(self, base_addr, offsets, pointer_size=4):
        if not self.pm:
            raise RuntimeError("pymem required for pointer resolution")
        cur = int(base_addr)
        # If offsets empty, return base
        if not offsets:
            return cur
        try:
            for off in offsets:
                # read pointer at cur
                if pointer_size == 8:
                    # 64-bit
                    val = self.pm.read_longlong(cur)
                else:
                    val = self.pm.read_int(cur)
                if val == 0:
                    cur = cur + off
                else:
                    cur = val + off
            return cur
        except Exception:
            # fallback simpler: read at (cur + off) each time
            cur = int(base_addr)
            try:
                for off in offsets:
                    cur = self.pm.read_int(cur + off)
                return cur
            except Exception as e:
                raise

# ---------------------------
# UI / App
# ---------------------------
PORTRAIT_WIDTH = 480
PORTRAIT_HEIGHT = 400

class TrainerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Hill Climb Racing Trainer (Cute Portrait)")
        try:
            if os.path.exists("Icon/icon.ico"):
                self.root.iconbitmap("Icon/icon.ico")
        except Exception:
            pass

        # memory
        self.mem = MemHelper()
        self.base_address = 0
        self.module_base = 0

        # freeze control
        self.fuel_freeze_event = threading.Event()
        self.fuel_thread = None
        self.fuel_freezing = False

        # load images
        self.info_img = self._load_icon("Icon/info.ico", (28,28))
        self.boost_img = self._load_icon("Icon/boost.ico", (64,64))

        # UI vars
        self.coin_var = tk.StringVar(value="0")
        self.diamond_var = tk.StringVar(value="0")
        self.fuel_var = tk.StringVar(value="100.00")  # float-like string
        self.boost_var = tk.StringVar(value="0")

        # Load config if exists
        try:
            if os.path.exists(CONFIG_PATH):
                with open(CONFIG_PATH, "r") as fh:
                    data = json.load(fh)
                self.coin_var.set(data.get("coin", "0"))
                self.diamond_var.set(data.get("diamond", "0"))
                self.fuel_var.set(data.get("fuel", "100.00"))
                self.boost_var.set(data.get("boost", "0"))
                global game, module
                if game is None:
                    game = data.get("game")
                if module is None:
                    module = data.get("module")
        except Exception:
            pass

        # Build UI
        self._build_ui()

        # run initial attach & read
        self.root.after(100, self.startup_attach_and_read)

    def _load_icon(self, path, size):
        if PIL_AVAILABLE and os.path.exists(path):
            try:
                im = Image.open(path).convert("RGBA")
                im = im.resize(size, Image.LANCZOS)
                return ImageTk.PhotoImage(im)
            except Exception:
                return None
        return None

    def _build_ui(self):
        main = tk.Frame(self.root)
        main.pack(fill="both", expand=True, padx=10, pady=10)

        # Title
        title = tk.Label(main, text="Hill Climb Racing Racing", font=("Arial", 20, "bold"))
        title.pack(pady=10)

        # Coins
        coins_frame = tk.Frame(main)
        coins_frame.pack(fill="x", pady=5)
        tk.Label(coins_frame, text="Coins").pack(side="left")
        tk.Entry(coins_frame, textvariable=self.coin_var).pack(side="left", padx=5)
        tk.Button(coins_frame, text="Set", command=self.set_coins).pack(side="left", padx=5)
        tk.Button(coins_frame, text="+100M", command=self.add_100m_coins).pack(side="left", padx=5)

        # Diamonds
        diamonds_frame = tk.Frame(main)
        diamonds_frame.pack(fill="x", pady=5)
        tk.Label(diamonds_frame, text="Diamonds").pack(side="left")
        tk.Entry(diamonds_frame, textvariable=self.diamond_var).pack(side="left", padx=5)
        tk.Button(diamonds_frame, text="Set", command=self.set_diamonds).pack(side="left", padx=5)
        tk.Button(diamonds_frame, text="+100M", command=self.add_100m_diamonds).pack(side="left", padx=5)

        # Fuel
        fuel_frame = tk.Frame(main)
        fuel_frame.pack(fill="x", pady=5)
        tk.Label(fuel_frame, text="Fuel (freeze)").pack(side="left")
        tk.Entry(fuel_frame, textvariable=self.fuel_var).pack(side="left", padx=5)
        self.fuel_toggle_btn = tk.Button(fuel_frame, text="Infinite Fuel: OFF", command=self.toggle_fuel)
        self.fuel_toggle_btn.pack(side="left", padx=5)

        # Boosts
        boost_frame = tk.Frame(main)
        boost_frame.pack(fill="x", pady=5)
        tk.Label(boost_frame, text="Boosts (buy)").pack(side="left")
        tk.Entry(boost_frame, textvariable=self.boost_var).pack(side="left", padx=5)
        if self.info_img:
            btn_info = tk.Button(boost_frame, image=self.info_img, command=self.show_boost_instructions)
        else:
            btn_info = tk.Button(boost_frame, text="i", command=self.show_boost_instructions)
        btn_info.pack(side="left", padx=5)
        tk.Button(boost_frame, text="Set", command=self.set_boosts).pack(side="left", padx=5)
        tk.Button(boost_frame, text="Recalibrate Pointer", command=self.recalibrate_boosts).pack(side="left", padx=5)

        # status label
        self.status_label = tk.Label(main, text="Initializing...")
        self.status_label.pack(pady=10)

        # bottom controls
        tk.Button(main, text="Hotkeys & Save", command=self.open_hotkeys_window).pack(pady=10)

    def hotkey_keypress(self, event, var):
        if event.keysym in ('Control_L', 'Control_R', 'Shift_L', 'Shift_R', 'Alt_L', 'Alt_R'):
            return "break"
        modifiers = []
        if event.state & 4:  # Control
            modifiers.append('ctrl')
        if event.state & 1:  # Shift
            modifiers.append('shift')
        if event.state & 8:  # Alt (Mod1)
            modifiers.append('alt')
        key = event.keysym.lower()
        hotkey = '+'.join(modifiers + [key]) if key else '+'.join(modifiers)
        var.set(hotkey)
        return "break"

    def register_hotkey(self, title, mode_var, val_var, hk_var, act_var, previous_hk):
        if act_var.get():
            hk = hk_var.get().strip()
            if not hk:
                messagebox.showerror("Hotkey", "Enter a hotkey.")
                act_var.set(False)
                return previous_hk
            try:
                intval = int(val_var.get())
            except:
                messagebox.showerror("Value", "Enter integer value.")
                act_var.set(False)
                return previous_hk
            def cb():
                if title.lower().startswith("coins"):
                    addr = self.compute_coins_addr()
                    if mode_var.get() == "Set":
                        self.root.after(10, lambda: self._write_safe_uint(addr, intval))
                    else:
                        def inc():
                            try:
                                cur = self.mem.read_uint(addr)
                            except:
                                cur = 0
                            self._write_safe_uint(addr, cur + intval)
                        self.root.after(10, inc)
                else:
                    addr = self.compute_diamonds_addr()
                    if mode_var.get() == "Set":
                        self.root.after(10, lambda: self._write_safe_uint(addr, intval))
                    else:
                        def inc2():
                            try:
                                cur = self.mem.read_uint(addr)
                            except:
                                cur = 0
                            self._write_safe_uint(addr, cur + intval)
                        self.root.after(10, inc2)
            try:
                keyboard.add_hotkey(hk, cb)
                self.registered_hotkeys.append({'hotkey': hk, 'cb': cb})
                self.status_label.config(text=f"Registered hotkey {hk}")
                return hk
            except Exception as e:
                messagebox.showerror("Hotkey", f"Failed to register: {e}")
                act_var.set(False)
                return previous_hk
        else:
            hk = hk_var.get().strip()
            try:
                keyboard.remove_hotkey(previous_hk)
            except Exception:
                try:
                    keyboard.clear_all_hotkeys()
                    self.registered_hotkeys.clear()
                except:
                    pass
            return previous_hk

    def register_fuel_hotkey(self, hk_var, act_var, previous_hk):
        if act_var.get():
            hk = hk_var.get().strip()
            if not hk:
                messagebox.showerror("Hotkey", "Enter a hotkey for fuel toggle.")
                act_var.set(False)
                return previous_hk
            def fuel_cb():
                self.root.after(10, lambda: self.toggle_fuel())
            try:
                keyboard.add_hotkey(hk, fuel_cb)
                self.registered_hotkeys.append({'hotkey': hk, 'cb': fuel_cb})
                self.status_label.config(text=f"Registered fuel hotkey {hk}")
                return hk
            except Exception as e:
                messagebox.showerror("Hotkey", f"Failed to register: {e}")
                act_var.set(False)
                return previous_hk
        else:
            hk = hk_var.get().strip()
            try:
                keyboard.remove_hotkey(previous_hk)
            except:
                try:
                    keyboard.clear_all_hotkeys()
                    self.registered_hotkeys.clear()
                except:
                    pass
            return previous_hk

    # ---------------------------
    # Start: attach to process and auto-read coins/diamonds
    # ---------------------------
    def startup_attach_and_read(self):
        # Check game variable
        global game, module
        if not game:
            messagebox.showerror("Game Not Set", "Please set the `game` variable inside the script before running. Exiting.")
            self.root.destroy()
            return
        try:
            # attach mem
            self.status_label.config(text=f"Attaching to {game}...")
            self.root.update()
            self.mem.attach_by_name(game)
            self.status_label.config(text=f"Attached to PID {self.mem.pid}")
            # resolve base addresses using provided funcs if pymem available
            if PYMEM_AVAILABLE:
                try:
                    self.base_address = get_base_address(game)
                except Exception:
                    self.base_address = 0
                if module:
                    try:
                        self.module_base = get_module_base_address(game, module)
                    except Exception:
                        self.module_base = 0
                else:
                    self.module_base = 0
            # auto-read coins and diamonds
            try:
                coins_addr = int(self.base_address) + COINS_OFFSET
                diamonds_addr = int(self.base_address) + DIAMONDS_OFFSET
                # read (uint)
                try:
                    cval = self.mem.read_uint(coins_addr)
                except Exception:
                    cval = 0
                try:
                    dval = self.mem.read_uint(diamonds_addr)
                except Exception:
                    dval = 0
                self.coin_var.set(str(cval))
                self.diamond_var.set(str(dval))
                self.status_label.config(text=f"Ready. Coins: {cval} Diamonds: {dval}")
            except Exception as e:
                # if reading fails, still allow user to proceed
                self.status_label.config(text=f"Ready (couldn't auto-read coins/diamonds): {e}")
        except Exception as e:
            messagebox.showerror("Attach failed", f"Could not find or attach to process '{game}'. Error: {e}\nThe trainer will now exit.")
            self.root.destroy()
            return

    # ---------------------------
    # Coins / Diamonds handlers
    # ---------------------------
    def _write_safe_uint(self, addr, value):
        try:
            if value < 0 or value > 0xFFFFFFFF:
                messagebox.showerror("Range error", "Value out of 32-bit unsigned range.")
                return False
            self.mem.write_uint(addr, int(value))
            return True
        except Exception as e:
            messagebox.showerror("Write error", str(e))
            return False

    def compute_coins_addr(self):
        if not self.base_address:
            raise RuntimeError("Base address unknown.")
        return int(self.base_address) + COINS_OFFSET

    def compute_diamonds_addr(self):
        if not self.base_address:
            raise RuntimeError("Base address unknown.")
        return int(self.base_address) + DIAMONDS_OFFSET

    def set_coins(self):
        s = self.coin_var.get().strip()
        try:
            v = int(s)
        except:
            messagebox.showerror("Invalid", "Enter a valid integer for coins.")
            return
        try:
            addr = self.compute_coins_addr()
            if self._write_safe_uint(addr, v):
                self.status_label.config(text=f"Coins set to {v}")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def add_100m_coins(self):
        try:
            addr = self.compute_coins_addr()
            try:
                cur = self.mem.read_uint(addr)
            except Exception:
                cur = 0
            new = cur + 100_000_000
            self.coin_var.set(str(new))
            self._write_safe_uint(addr, new)
            self.status_label.config(text=f"Added 100M. Coins: {new}")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def set_diamonds(self):
        s = self.diamond_var.get().strip()
        try:
            v = int(s)
        except:
            messagebox.showerror("Invalid", "Enter a valid integer for diamonds.")
            return
        try:
            addr = self.compute_diamonds_addr()
            if self._write_safe_uint(addr, v):
                self.status_label.config(text=f"Diamonds set to {v}")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def add_100m_diamonds(self):
        try:
            addr = self.compute_diamonds_addr()
            try:
                cur = self.mem.read_uint(addr)
            except Exception:
                cur = 0
            new = cur + 100_000_000
            self.diamond_var.set(str(new))
            self._write_safe_uint(addr, new)
            self.status_label.config(text=f"Added 100M. Diamonds: {new}")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    # ---------------------------
    # Fuel freeze (writes float(100.00) as bytes repeatedly)
    # ---------------------------
    def toggle_fuel(self):
        if not self.fuel_freezing:
            # start freeze
            try:
                if not self.base_address:
                    raise RuntimeError("Base address unknown.")
                fuel_base = int(self.base_address) + FUEL_BASE_OFFSET
                try:
                    fuel_addr = self.mem.resolve_pointer(fuel_base, FUEL_OFFSETS)
                except Exception:
                    fuel_addr = fuel_base + (FUEL_OFFSETS[0] if FUEL_OFFSETS else 0)
                self.fuel_addr = fuel_addr
            except Exception as e:
                messagebox.showerror("Fuel pointer error", f"Could not resolve fuel address: {e}")
                return
            # start thread
            self.fuel_freeze_event.clear()
            self.fuel_thread = threading.Thread(target=self._fuel_freeze_worker, daemon=True)
            self.fuel_freezing = True
            self.fuel_thread.start()
            self.fuel_toggle_btn.config(text="Infinite Fuel: ON")
            self.status_label.config(text="Infinite Fuel enabled")
        else:
            # stop
            self.fuel_freeze_event.set()
            self.fuel_freezing = False
            self.fuel_toggle_btn.config(text="Infinite Fuel: OFF")
            self.status_label.config(text="Infinite Fuel disabled")

    def _fuel_freeze_worker(self):
        # pack float value to bytes once
        try:
            val = float(self.fuel_var.get() or "100.0")
        except:
            val = 100.0
        packed = struct.pack('<f', val)  # float bytes
        # continuous write until event set
        interval = 0.11
        while not self.fuel_freeze_event.is_set():
            try:
                # write the float bytes so memory contains float bits (even if we write as raw bytes)
                self.mem.write_bytes(self.fuel_addr, packed)
            except Exception as e:
                # update status and break if persistent failure
                self.status_label.config(text=f"Fuel write error: {e}")
            time.sleep(interval)

    # ---------------------------
    # Boosts and recalibration
    # ---------------------------
    def compute_boost_base(self):
        if not self.module_base:
            raise RuntimeError("Module base unknown. Set module variable if needed.")
        return int(self.module_base) + BOOST_BASE_OFFSET

    def set_boosts(self):
        s = self.boost_var.get().strip()
        try:
            v = int(s)
        except:
            messagebox.showerror("Invalid", "Enter integer (1..9999).")
            return
        if v <= 0 or v >= 10000:
            messagebox.showerror("Range", "Boosts must be >0 and <10000.")
            return
        # user must have opened boost buy popup in-game
        proceed = messagebox.askyesno("Proceed?", "Make sure you've opened the Boost buy popup in-game before using this. Proceed to write?")
        if not proceed:
            return
        try:
            base = self.compute_boost_base()
            resolved = self.mem.resolve_pointer(base, BOOST_OFFSETS)
            self.mem.write_int(resolved, v)
            messagebox.showinfo("Done", f"Wrote boosts={v} at {hex(resolved)}")
            self.status_label.config(text=f"Boosts set: {v}")
        except Exception as e:
            messagebox.showerror("Write failed", str(e))

    def recalibrate_boosts(self):
        # ask first per your spec
        ok = messagebox.askyesno("Calibration check", "Is the boost pointer working correctly right now? (Yes = leave as-is, No = attempt recalibration)")
        if ok:
            messagebox.showinfo("Calibration", "Pointer left as-is.")
            return
        # attempt secondary then third offsets
        try:
            base = self.compute_boost_base()
        except Exception as e:
            messagebox.showerror("Error", f"Module base unknown: {e}")
            return
        for offsets in (BOOST_SECONDARY_OFFSETS, BOOST_THIRD_OFFSETS):
            try:
                resolved = self.mem.resolve_pointer(base, offsets)
                try:
                    val = self.mem.read_int(resolved)
                    self.status_label.config(text=f"Recalibrated. Addr {hex(resolved)} val {val}")
                    messagebox.showinfo("Recalibration success", f"Used offsets {offsets}. Resolved addr {hex(resolved)} with value {val}")
                    return
                except Exception:
                    continue
            except Exception:
                continue
        messagebox.showerror("Recalibration failed", "Could not recalibrate with provided alternate offsets.")

    # ---------------------------
    # Boost instructions popup (scrollable) with boost icon shown
    # ---------------------------
    def show_boost_instructions(self):
        top = tk.Toplevel(self.root)
        top.title("Boost Instructions")
        # show boost icon at top if available
        if self.boost_img:
            lbl = tk.Label(top, image=self.boost_img)
            lbl.pack(pady=10)
        # text box
        text = tk.Text(top, wrap="word", height=10, width=50)
        text.pack(padx=10, pady=10)
        message = (
            "Before buying a huge number of boosts, you first need to click on the boost icon in your game which will popup the section where you can buy boosts.\n\n"
            "After that, return to the application and give your desired number in the entry and click Set.\n\n"
            "Then, return to your game and click on the “-” icon to lower your boost count and you can finally buy the required boosts. Enjoy!"
        )
        text.insert("1.0", message)
        text.config(state="disabled")
        tk.Button(top, text="OK", command=top.destroy).pack(pady=10)

    # ---------------------------
    # Hotkeys window with Save inside
    # ---------------------------
    def open_hotkeys_window(self):
        wh = tk.Toplevel(self.root)
        wh.title("Hotkeys & Save Profile")

        # header
        tk.Label(wh, text="Hotkeys (Coins / Diamonds / Fuel toggle)").pack(pady=10)

        container = tk.Frame(wh)
        container.pack(fill="both", expand=True, padx=10, pady=10)

        self.registered_hotkeys = []  # store dicts

        def make_hotkey_row(title):
            row = tk.Frame(container)
            row.pack(fill="x", pady=5)
            tk.Label(row, text=title).pack(side="left", padx=5)
            mode_var = tk.StringVar(value="Set")
            ttk.OptionMenu(row, mode_var, "Set", "Set", "Increase").pack(side="left", padx=5)
            val_var = tk.StringVar(value="100000")
            tk.Entry(row, textvariable=val_var).pack(side="left", padx=5)
            hk_var = tk.StringVar(value="")
            hk_entry = tk.Entry(row, textvariable=hk_var)
            hk_entry.pack(side="left", padx=5)
            hk_entry.bind("<KeyPress>", lambda e: self.hotkey_keypress(e, hk_var))
            ToolTip(hk_entry, "Please Enter Your Shortcut Key Here...")
            act_var = tk.BooleanVar(value=False)
            previous_hk = [hk_var.get()]  # use list for mutable
            def on_hk_change(*args):
                if act_var.get() and hk_var.get() != previous_hk[0]:
                    try:
                        keyboard.remove_hotkey(previous_hk[0])
                    except:
                        pass
                    act_var.set(False)
            hk_var.trace("w", on_hk_change)
            tk.Checkbutton(row, text="Active", variable=act_var, command=lambda: previous_hk.append(self.register_hotkey(title, mode_var, val_var, hk_var, act_var, previous_hk[0])) and previous_hk.pop(0)).pack(side="left", padx=5)
            tk.Button(row, text="Clear", command=lambda: [hk_var.set(""), act_var.set(False)]).pack(side="left", padx=5)
            return (mode_var, val_var, hk_var, act_var)

        # coins & diamonds rows
        coin_tuple = make_hotkey_row("Coins")
        diam_tuple = make_hotkey_row("Diamonds")

        # fuel toggle row
        frow = tk.Frame(container)
        frow.pack(fill="x", pady=5)
        tk.Label(frow, text="Fuel Toggle").pack(side="left", padx=5)
        fhk_var = tk.StringVar(value="")
        fhk_entry = tk.Entry(frow, textvariable=fhk_var)
        fhk_entry.pack(side="left", padx=5)
        fhk_entry.bind("<KeyPress>", lambda e: self.hotkey_keypress(e, fhk_var))
        ToolTip(fhk_entry, "Please Enter Your Shortcut Key Here...")
        factive = tk.BooleanVar(value=False)
        f_previous_hk = [fhk_var.get()]  # mutable
        def f_on_hk_change(*args):
            if factive.get() and fhk_var.get() != f_previous_hk[0]:
                try:
                    keyboard.remove_hotkey(f_previous_hk[0])
                except:
                    pass
                factive.set(False)
        fhk_var.trace("w", f_on_hk_change)
        tk.Checkbutton(frow, text="Active", variable=factive, command=lambda: f_previous_hk.append(self.register_fuel_hotkey(fhk_var, factive, f_previous_hk[0])) and f_previous_hk.pop(0)).pack(side="left", padx=5)
        tk.Button(frow, text="Clear", command=lambda: [fhk_var.set(""), factive.set(False)]).pack(side="left", padx=5)

        # Load from config
        try:
            if os.path.exists(CONFIG_PATH):
                with open(CONFIG_PATH, "r") as fh:
                    data = json.load(fh)
                if "hotkeys" in data:
                    h = data["hotkeys"]
                    if "coins" in h:
                        mode_var, val_var, hk_var, act_var = coin_tuple
                        mode_var.set(h["coins"].get("mode", "Set"))
                        val_var.set(h["coins"].get("value", "100000"))
                        hk_var.set(h["coins"].get("hotkey", ""))
                        active = h["coins"].get("active", False)
                        act_var.set(active)
                        if active:
                            self.register_hotkey("Coins", mode_var, val_var, hk_var, act_var, hk_var.get())
                    if "diamonds" in h:
                        mode_var, val_var, hk_var, act_var = diam_tuple
                        mode_var.set(h["diamonds"].get("mode", "Set"))
                        val_var.set(h["diamonds"].get("value", "100000"))
                        hk_var.set(h["diamonds"].get("hotkey", ""))
                        active = h["diamonds"].get("active", False)
                        act_var.set(active)
                        if active:
                            self.register_hotkey("Diamonds", mode_var, val_var, hk_var, act_var, hk_var.get())
                    if "fuel" in h:
                        fhk_var.set(h["fuel"].get("hotkey", ""))
                        active = h["fuel"].get("active", False)
                        factive.set(active)
                        if active:
                            self.register_fuel_hotkey(fhk_var, factive, fhk_var.get())
        except Exception:
            pass

        # Save button (only here)
        def save_profile():
            coin_mode_var, coin_val_var, coin_hk_var, coin_act_var = coin_tuple
            diam_mode_var, diam_val_var, diam_hk_var, diam_act_var = diam_tuple
            hotkeys = {
                "coins": {"mode": coin_mode_var.get(), "value": coin_val_var.get(), "hotkey": coin_hk_var.get(), "active": coin_act_var.get()},
                "diamonds": {"mode": diam_mode_var.get(), "value": diam_val_var.get(), "hotkey": diam_hk_var.get(), "active": diam_act_var.get()},
                "fuel": {"hotkey": fhk_var.get(), "active": factive.get()}
            }
            data = {
                "game": game,
                "module": module,
                "coin": self.coin_var.get(),
                "diamond": self.diamond_var.get(),
                "fuel": self.fuel_var.get(),
                "boost": self.boost_var.get(),
                "hotkeys": hotkeys
            }
            try:
                with open(CONFIG_PATH, "w") as fh:
                    json.dump(data, fh, indent=2)
                messagebox.showinfo("Saved", f"Profile saved to {CONFIG_PATH}")
            except Exception as e:
                messagebox.showerror("Save error", str(e))
        tk.Button(wh, text="Save Profile", command=save_profile).pack(pady=10)

        tk.Button(wh, text="Close", command=wh.destroy).pack(pady=10)

    # ---------------------------
    # Save on exit & cleanup
    # ---------------------------
    def cleanup_and_exit(self):
        try:
            if self.fuel_freezing:
                self.fuel_freeze_event.set()
                time.sleep(0.12)
        except:
            pass
        try:
            # clear hotkeys
            if KEYBOARD_AVAILABLE:
                try:
                    keyboard.clear_all_hotkeys()
                except:
                    pass
        except:
            pass
        try:
            self.mem.detach()
        except:
            pass
        self.root.destroy()

# ---------------------------
# Main runner
# ---------------------------
def main():
    # Basic check: require game to be set by user
    root = tk.Tk()
    root.geometry(f"{PORTRAIT_WIDTH}x{PORTRAIT_HEIGHT}")
    app = TrainerApp(root)
    # properly handle closing
    root.protocol("WM_DELETE_WINDOW", app.cleanup_and_exit)
    root.mainloop()

if __name__ == "__main__":
    main()