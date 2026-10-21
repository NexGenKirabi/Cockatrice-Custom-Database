import os
import json
import xml.etree.ElementTree as ET
import requests
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
import uuid
from datetime import datetime
import threading
from PIL import Image, ImageTk
import io
import re

try:
    from CockatriceArt import scan_card_name
except ImportError:
    def scan_card_name(filepath):
        return ""

CONFIG_FILE = "config.json"
MTGJSON_URL = "https://mtgjson.com/api/v5/AtomicCards.json"
DB_FILE = "AtomicCards.json"

class CockatriceSetManager:
    def __init__(self, root):
        self.root = root
        self.root.title("Cockatrice Custom Card Manager")
        self.root.geometry("550x640")
        
        self.config = self.load_config()
        self.current_xml_path = None
        self.tree = None
        self.root_xml = None
        self.valid_cards = {}
        
        self.setup_ui()
        self.check_first_run()
        self.init_database()

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        return {"last_file": "", "install_type": "", "portable_path": ""}

    def save_config(self):
        with open(CONFIG_FILE, "w") as f:
            json.dump(self.config, f)

    def check_first_run(self):
        if not self.config.get("install_type"):
            response = messagebox.askquestion("Cockatrice Install", "Is your Cockatrice installation Portable? (Select 'No' for Standard)")
            if response == 'yes':
                self.config["install_type"] = "portable"
                self.config["portable_path"] = filedialog.askdirectory(title="Select Cockatrice Portable Folder")
            else:
                self.config["install_type"] = "standard"
            self.save_config()

        last_file = self.config.get("last_file")
        if last_file and os.path.exists(last_file):
            if messagebox.askyesno("Resume", f"Continue working on last file?\n{os.path.basename(last_file)}"):
                self.load_xml(last_file)

    def setup_ui(self):
        self.lbl_status = ttk.Label(self.root, text="No XML file loaded", font=("Arial", 10, "italic"))
        self.lbl_status.pack(pady=10)
        
        self.lbl_db_status = ttk.Label(self.root, text="Database Status: Checking...", foreground="blue")
        self.lbl_db_status.pack(pady=5)

        btn_frame = ttk.Frame(self.root)
        btn_frame.pack(pady=10)

        ttk.Button(btn_frame, text="Create New File", command=self.create_new_file).grid(row=0, column=0, padx=5, pady=5)
        ttk.Button(btn_frame, text="Open Existing File", command=self.open_existing_file).grid(row=0, column=1, padx=5, pady=5)
        
        ttk.Button(self.root, text="Update Card Database", command=self.download_database).pack(pady=5)
        ttk.Button(self.root, text="Add Cards to Set", command=self.add_cards_flow).pack(pady=10)
        ttk.Button(self.root, text="View / Edit Set Cards", command=self.open_card_manager).pack(pady=5)
        ttk.Button(self.root, text="Generate Sharing Link", command=self.share_file).pack(pady=5)
        ttk.Button(self.root, text="Download Cards from URL", command=self.download_from_url).pack(pady=5)

    # --- Database & Validation Logic ---

    def init_database(self):
        if not os.path.exists(DB_FILE):
            self.download_database()
        else:
            self.load_database()

    def download_database(self):
        self.lbl_db_status.config(text="Database Status: Downloading...", foreground="orange")
        self.root.update_idletasks()
        
        def fetch():
            try:
                response = requests.get(MTGJSON_URL)
                with open(DB_FILE, "wb") as f:
                    f.write(response.content)
                self.root.after(0, self.load_database)
            except Exception as e:
                self.root.after(0, lambda: self.lbl_db_status.config(text=f"Database Download Failed", foreground="red"))
                print(e)
                
        threading.Thread(target=fetch, daemon=True).start()

    def load_database(self):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.valid_cards = {self.normalize_name(name): name for name in data["data"].keys()}
            self.lbl_db_status.config(text=f"Database Status: Loaded ({len(self.valid_cards)} cards)", foreground="green")
        except Exception as e:
            self.lbl_db_status.config(text="Database Status: Failed to load", foreground="red")
            print(e)

    def normalize_name(self, name):
        return re.sub(r'[^a-z0-9]', '', str(name).lower())

    def resolve_card_name(self, img_path):
        ocr_name = scan_card_name(img_path)
        norm_ocr = self.normalize_name(ocr_name)
        file_name = os.path.splitext(os.path.basename(img_path))[0]
        norm_file = self.normalize_name(file_name)
        
        custom_dict_path = "custom_names.json"
        if os.path.exists(custom_dict_path):
            with open(custom_dict_path, "r") as f:
                custom_names = json.load(f)
                if norm_ocr and norm_ocr in custom_names:
                    return custom_names[norm_ocr]
                if norm_file and norm_file in custom_names:
                    return custom_names[norm_file]

        if norm_ocr and norm_ocr in self.valid_cards:
            return self.valid_cards[norm_ocr]
        if norm_file and norm_file in self.valid_cards:
            return self.valid_cards[norm_file]
            
        return self.ask_user_for_name(img_path, ocr_name, file_name)

    def ask_user_for_name(self, img_path, ocr_guess, file_guess):
        dialog = tk.Toplevel(self.root)
        dialog.title("Uncertain Card Name")
        dialog.geometry("400x550")
        dialog.grab_set()

        try:
            img = Image.open(img_path)
            img.thumbnail((300, 400)) 
            photo = ImageTk.PhotoImage(img)
            lbl_img = tk.Label(dialog, image=photo)
            lbl_img.image = photo 
            lbl_img.pack(pady=10)
        except Exception as e:
            tk.Label(dialog, text="[Image Load Failed]").pack()

        info_text = f"Could not verify card against database.\nOCR Guess: {ocr_guess or 'None'}\nFile Guess: {file_guess}"
        tk.Label(dialog, text=info_text, justify="center").pack(pady=5)
        
        tk.Label(dialog, text="Enter Exact Card Name:").pack()
        entry_var = tk.StringVar(value=ocr_guess or file_guess)
        entry = tk.Entry(dialog, textvariable=entry_var, width=40)
        entry.pack(pady=5)
        entry.focus_set()

        result = [""]

        def submit(event=None):
            val = entry_var.get().strip()
            if self.normalize_name(val) not in self.valid_cards:
                if not messagebox.askyesno("Warning", "Name not found in MTG database. Use anyway?", parent=dialog):
                    return
            result[0] = val
            dialog.destroy()

        ttk.Button(dialog, text="Confirm", command=submit).pack(pady=10)
        dialog.bind("<Return>", submit)
        
        self.root.wait_window(dialog)
        return result[0]

    # --- Card Manager Window (View, Edit, Delete) ---

    def open_card_manager(self):
        if not self.current_xml_path or not self.root_xml:
            messagebox.showwarning("Warning", "Open or create an XML file first.")
            return

        mgr_win = tk.Toplevel(self.root)
        mgr_win.title("Manage Set Cards")
        mgr_win.geometry("800x550")
        mgr_win.grab_set()

        # Left side: Treeview list of cards
        frame_list = ttk.Frame(mgr_win)
        frame_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)

        tree = ttk.Treeview(frame_list, columns=("Name", "Set"), show="headings", selectmode="browse")
        tree.heading("Name", text="Card Name")
        tree.heading("Set", text="Set Code")
        tree.column("Name", width=280)
        tree.column("Set", width=80)
        
        tree_scroll = ttk.Scrollbar(frame_list, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=tree_scroll.set)
        
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # Right side: Image Preview & Actions Frame
        frame_right = ttk.Frame(mgr_win, width=300)
        frame_right.pack(side=tk.RIGHT, fill=tk.BOTH, padx=10, pady=10)

        preview_container = ttk.LabelFrame(frame_right, text="Card Preview")
        preview_container.pack(pady=5, fill=tk.BOTH, expand=True)

        lbl_preview = ttk.Label(preview_container, text="[Select a Card]", anchor="center")
        lbl_preview.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Dictionary to securely map Treeview item IDs to XML card elements
        item_to_card = {}

        def refresh_card_list():
            item_to_card.clear()
            for item in tree.get_children():
                tree.delete(item)
            
            cards_elem = self.root_xml.find("cards")
            if cards_elem is not None:
                for card in cards_elem.findall("card"):
                    name_elem = card.find("name")
                    set_elem = card.find("set")
                    c_name = name_elem.text if name_elem is not None else "Unknown"
                    c_set = set_elem.text if set_elem is not None else ""
                    
                    # Insert into tree and map its unique row ID to the XML element
                    row_id = tree.insert("", tk.END, values=(c_name, c_set))
                    item_to_card[row_id] = card

        refresh_card_list()

        def on_card_select(event):
            selected = tree.selection()
            if not selected:
                return
            row_id = selected[0]
            card_elem = item_to_card.get(row_id)
            if not card_elem:
                return

            set_elem = card_elem.find("set")
            picurl = set_elem.get("picurl") if set_elem is not None else None

            if picurl:
                lbl_preview.config(image="", text="Loading preview...")
                def fetch_img():
                    try:
                        headers = {'User-Agent': 'Mozilla/5.0'}
                        res = requests.get(picurl, headers=headers)
                        if res.status_code == 200:
                            img_data = io.BytesIO(res.content)
                            img = Image.open(img_data)
                            img.thumbnail((250, 350))
                            photo = ImageTk.PhotoImage(img)
                            
                            def update_ui():
                                lbl_preview.config(image=photo, text="")
                                lbl_preview.image = photo
                            mgr_win.after(0, update_ui)
                    except:
                        mgr_win.after(0, lambda: lbl_preview.config(image="", text="[Preview Failed]"))
                threading.Thread(target=fetch_img, daemon=True).start()
            else:
                lbl_preview.config(image="", text="[No Image URL Provided]")

        tree.bind("<<TreeviewSelect>>", on_card_select)

        def edit_selected_card():
            selected = tree.selection()
            if not selected:
                messagebox.showwarning("Warning", "Select a card to edit.", parent=mgr_win)
                return
            card_elem = item_to_card.get(selected[0])
            if not card_elem:
                return
                
            name_elem = card_elem.find("name")
            current_name = name_elem.text if name_elem is not None else ""
            new_name = simpledialog.askstring("Edit Card Name", "Enter new card name:", initialvalue=current_name, parent=mgr_win)
            
            if new_name:
                name_elem.text = new_name.strip()
                ET.indent(self.tree, space="\t", level=0)
                self.tree.write(self.current_xml_path, encoding="utf-8", xml_declaration=True)
                refresh_card_list()
                messagebox.showinfo("Success", "Card updated!", parent=mgr_win)

        def delete_selected_card():
            selected = tree.selection()
            if not selected:
                messagebox.showwarning("Warning", "Select a card to delete.", parent=mgr_win)
                return
            card_elem = item_to_card.get(selected[0])
            if not card_elem:
                return
            
            if messagebox.askyesno("Confirm Delete", "Are you sure you want to delete this card from the set?", parent=mgr_win):
                cards_elem = self.root_xml.find("cards")
                if cards_elem is not None:
                    cards_elem.remove(card_elem)
                    ET.indent(self.tree, space="\t", level=0)
                    self.tree.write(self.current_xml_path, encoding="utf-8", xml_declaration=True)
                    refresh_card_list()
                    lbl_preview.config(image="", text="[Select a Card]")
                    messagebox.showinfo("Success", "Card deleted!", parent=mgr_win)

        btn_action_frame = ttk.Frame(frame_right)
        btn_action_frame.pack(fill=tk.X, pady=5)

        ttk.Button(btn_action_frame, text="Edit Name", command=edit_selected_card).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)
        ttk.Button(btn_action_frame, text="Delete Card", command=delete_selected_card).pack(side=tk.RIGHT, expand=True, fill=tk.X, padx=2)
        
        ttk.Button(frame_right, text="Close Manager", command=mgr_win.destroy).pack(fill=tk.X, pady=10)

    # --- XML & Network Management ---

    def init_blank_xml(self):
        root = ET.Element("cockatrice_carddatabase", version="4", xmlns_xsi="http://www.w3.org/2001/XMLSchema-instance")
        info = ET.SubElement(root, "info")
        ET.SubElement(info, "author").text = "CustomCardManager"
        ET.SubElement(info, "createdAt").text = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        ET.SubElement(root, "sets")
        ET.SubElement(root, "cards")
        return ET.ElementTree(root)

    def create_new_file(self):
        filename = simpledialog.askstring("New File", "Enter a name for the new custom card file:")
        if not filename: return
        if not filename.endswith(".xml"): filename += ".xml"
            
        save_path = filedialog.askdirectory(title="Where to save this file?")
        if not save_path: return
            
        full_path = os.path.join(save_path, filename)
        self.tree = self.init_blank_xml()
        self.root_xml = self.tree.getroot()
        self.current_xml_path = full_path
        self.tree.write(full_path, encoding="utf-8", xml_declaration=True)
        
        self.config["last_file"] = full_path
        self.save_config()
        self.lbl_status.config(text=f"Loaded: {filename}")

    def open_existing_file(self):
        filepath = filedialog.askopenfilename(filetypes=[("XML Files", "*.xml")])
        if filepath: self.load_xml(filepath)

    def load_xml(self, filepath):
        try:
            self.tree = ET.parse(filepath)
            self.root_xml = self.tree.getroot()
            self.current_xml_path = filepath
            self.config["last_file"] = filepath
            self.save_config()
            self.lbl_status.config(text=f"Loaded: {os.path.basename(filepath)}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to parse XML:\n{e}")

    def add_cards_flow(self):
        if not self.current_xml_path:
            messagebox.showwarning("Warning", "Create or open a file first.")
            return

        sets_elem = self.root_xml.find("sets")
        existing_sets = [s.find("name").text for s in sets_elem.findall("set") if s.find("name") is not None]
        
        set_choice = simpledialog.askstring("Set Target", f"Existing sets: {', '.join(existing_sets) if existing_sets else 'None'}\n\nEnter the Set Code to use or create:")
        if not set_choice: return
            
        if set_choice not in existing_sets:
            longname = simpledialog.askstring("New Set Details", "Enter the full Set Name (Longname):")
            new_set = ET.SubElement(sets_elem, "set")
            ET.SubElement(new_set, "name").text = set_choice
            ET.SubElement(new_set, "longname").text = longname or set_choice
            ET.SubElement(new_set, "settype").text = "Custom"
            ET.SubElement(new_set, "releasedate").text = datetime.today().strftime("%Y-%m-%d")

        images = filedialog.askopenfilenames(title="Select Card Images", filetypes=[("Images", "*.png;*.jpg;*.jpeg")])
        if not images: return

        cards_elem = self.root_xml.find("cards")
        
        for img_path in images:
            card_name = self.resolve_card_name(img_path)
            if not card_name:
                continue 
            
            pic_url = self.upload_to_catbox(img_path)
            if not pic_url:
                messagebox.showerror("Error", f"Failed to upload {card_name}. Skipping.")
                continue

            card_elem = ET.SubElement(cards_elem, "card")
            ET.SubElement(card_elem, "name").text = card_name
            set_node = ET.SubElement(card_elem, "set", rarity="Rare", uuid=set_choice + str(uuid.uuid4())[:4], picurl=pic_url)
            set_node.text = set_choice

        ET.indent(self.tree, space="\t", level=0)
        self.tree.write(self.current_xml_path, encoding="utf-8", xml_declaration=True)
        messagebox.showinfo("Success", f"Processing complete!")

    def upload_to_catbox(self, filepath):
        url = "https://catbox.moe/user/api.php"
        try:
            with open(filepath, 'rb') as f:
                payload = {'reqtype': 'fileupload'}
                files = {'fileToUpload': f}
                response = requests.post(url, data=payload, files=files)
            if response.status_code == 200:
                return response.text
            return None
        except:
            return None

    def share_file(self):
        if not self.current_xml_path: return
        link = self.upload_to_catbox(self.current_xml_path)
        if link:
            self.root.clipboard_clear()
            self.root.clipboard_append(link)
            messagebox.showinfo("Shared!", f"File uploaded successfully.\n\nLink copied to clipboard:\n{link}")
        else:
            messagebox.showerror("Error", "Failed to upload XML to Catbox.")

    def download_from_url(self):
        url = simpledialog.askstring("Download XML", "Enter the Catbox URL for the custom cards XML:")
        if not url:
            return
            
        url = url.strip()
        if not url.startswith("http"):
            messagebox.showerror("Error", "Invalid URL provided.")
            return

        save_path = filedialog.asksaveasfilename(
            title="Save Downloaded XML As...", 
            defaultextension=".xml",
            filetypes=[("XML Files", "*.xml")]
        )
        
        if not save_path:
            return

        self.lbl_status.config(text="Downloading XML...")
        self.root.update_idletasks()

        def fetch_xml():
            try:
                # 1. Use full browser headers to avoid getting redirected to HTML/bot-blocking pages
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
                }
                
                response = requests.get(url, headers=headers, allow_redirects=True)
                response.raise_for_status() 
                
                content = response.text.strip()

                # 2. Verify the file actually starts with XML or valid content (not HTML error pages or empty)
                if not content:
                    raise Exception("Downloaded file is completely empty.")
                
                if content.startswith("<html") or content.startswith("<!DOCTYPE html"):
                    raise Exception("URL returned an HTML web page instead of raw XML data. Ensure the direct download link is used.")

                # Save raw bytes to ensure clean formatting
                with open(save_path, "wb") as f:
                    f.write(response.content)
                
                self.root.after(0, lambda: messagebox.showinfo("Success", "File downloaded successfully!"))
                self.root.after(0, lambda: self.load_xml(save_path))
                
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("Error", f"Failed to download/parse file:\n{e}"))
                self.root.after(0, lambda: self.lbl_status.config(text="No XML file loaded"))

        threading.Thread(target=fetch_xml, daemon=True).start()

if __name__ == "__main__":
    root = tk.Tk()
    app = CockatriceSetManager(root)
    root.mainloop()