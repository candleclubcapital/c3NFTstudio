# nft_studio.py
import sys
import os
import json
import random
import shutil
from PIL import Image

from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QLineEdit, QFileDialog, QSpinBox, QMessageBox, QTabWidget,
    QGroupBox, QComboBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QTextEdit, QProgressBar
)
from PySide6.QtCore import Qt, QThread, Signal


# =========================================================
# Pillow resample helper (compat across versions)
# =========================================================
def _resample_lanczos():
    try:
        return Image.Resampling.LANCZOS
    except AttributeError:
        try:
            return Image.LANCZOS
        except AttributeError:
            return Image.BICUBIC


RESAMPLE_LANCZOS = _resample_lanczos()


# =========================================================
# Helpers for JSON persistence
# =========================================================
def load_json(path, default):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=4)


# =========================================================
# Worker thread for NFT generation
# =========================================================
class GenerationWorker(QThread):
    log_signal = Signal(str)
    progress_signal = Signal(int, int)
    done_signal = Signal(dict)

    def __init__(self, config, quantity):
        super().__init__()
        self.config = config
        self.quantity = quantity

    def run(self):
        stats = run_generation(
            self.config,
            self.quantity,
            log_callback=lambda msg: self.log_signal.emit(msg),
            progress_callback=lambda done, total: self.progress_signal.emit(done, total),
        )
        self.done_signal.emit(stats)


# =========================================================
# Main GUI
# =========================================================
class NFTGeneratorGUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("C3 NFT STUDIO")
        self.setGeometry(100, 100, 1360, 900)

        # Persistence stores
        self.saved_configs_path = os.path.join("configs", "saved_configs.json")
        self.saved_mappings_path = os.path.join("configs", "saved_mappings.json")

        self.configs = load_json(self.saved_configs_path, {})
        self.mappings = load_json(self.saved_mappings_path, {})

        # UI state
        self.active_config_name = None
        self.rarity_spinboxes = {}     # Trait rarity editors { "Layer:Trait": QSpinBox }
        self.layer_rarity_spin = {}    # Layer rarity editors { "Layer": QSpinBox }

        # Build UI
        layout = QVBoxLayout()
        self.tabs = QTabWidget()
        self.tabs.addTab(self.build_configs_tab(), "Configs (Layer Order)")
        self.tabs.addTab(self.build_mappings_tab(), "Trait Mappings")
        self.tabs.addTab(self.build_manager_tab(), "Config Manager")
        self.tabs.addTab(self.build_generation_tab(), "Generate NFTs")
        layout.addWidget(self.tabs)
        self.setLayout(layout)

        # Initial refresh
        self.refresh_config_lists()

    # =========================================================
    # TAB: Configs (Layer Order + metadata + size + dirs + excluded layers)
    # =========================================================
    def build_configs_tab(self):
        tab = QWidget()
        layout = QVBoxLayout()

        # --- Config Name ---
        name_row = QHBoxLayout()
        self.cfg_name_input = QLineEdit()
        self.cfg_name_input.setPlaceholderText("New config name or existing to overwrite...")
        name_row.addWidget(QLabel("Config Name"))
        name_row.addWidget(self.cfg_name_input)

        # --- Directories ---
        dir_box = QGroupBox("Directories")
        dir_layout = QVBoxLayout()

        # Layers dir
        l_row = QHBoxLayout()
        self.cfg_layers_dir = QLineEdit()
        btn_browse_layers = QPushButton("Browse Layers")
        btn_browse_layers.clicked.connect(self.cfg_browse_layers_dir)
        l_row.addWidget(QLabel("Layers Dir"))
        l_row.addWidget(self.cfg_layers_dir)
        l_row.addWidget(btn_browse_layers)

        # Output dir
        o_row = QHBoxLayout()
        self.cfg_output_dir = QLineEdit()
        btn_browse_output = QPushButton("Browse Output")
        btn_browse_output.clicked.connect(self.cfg_browse_output_dir)
        o_row.addWidget(QLabel("Output Dir"))
        o_row.addWidget(self.cfg_output_dir)
        o_row.addWidget(btn_browse_output)

        # Reload layers button
        reload_row = QHBoxLayout()
        self.btn_reload_layers = QPushButton("Reload Available Layers")
        self.btn_reload_layers.clicked.connect(self.cfg_reload_layers)
        reload_row.addStretch()
        reload_row.addWidget(self.btn_reload_layers)

        dir_layout.addLayout(l_row)
        dir_layout.addLayout(o_row)
        dir_layout.addLayout(reload_row)
        dir_box.setLayout(dir_layout)

        # --- Layer Order Builder + Excluded Layers ---
        order_box = QGroupBox("Layer Order (Configs are layer orders) & Excluded Layers")
        order_layout = QHBoxLayout()

        left_col = QVBoxLayout()
        self.available_layers = QListWidget()
        self.available_layers.setSelectionMode(QListWidget.ExtendedSelection)
        left_col.addWidget(QLabel("Available Layers"))
        left_col.addWidget(self.available_layers, 1)

        mid_col = QVBoxLayout()
        btn_add = QPushButton(">>")
        btn_add.clicked.connect(self.cfg_add_layers_to_order)
        btn_remove = QPushButton("<<")
        btn_remove.clicked.connect(self.cfg_remove_layers_from_order)
        btn_up = QPushButton("Move Up")
        btn_up.clicked.connect(self.cfg_move_layer_up)
        btn_down = QPushButton("Move Down")
        btn_down.clicked.connect(self.cfg_move_layer_down)
        mid_col.addWidget(btn_add)
        mid_col.addWidget(btn_remove)
        mid_col.addSpacing(12)
        mid_col.addWidget(btn_up)
        mid_col.addWidget(btn_down)
        mid_col.addStretch()

        right_col = QVBoxLayout()
        self.layer_order = QListWidget()
        self.layer_order.setSelectionMode(QListWidget.ExtendedSelection)
        right_col.addWidget(QLabel("Layer Order"))
        right_col.addWidget(self.layer_order, 1)

        # Excluded layers
        excl_row = QHBoxLayout()
        self.excluded_available_layers = QListWidget()
        self.excluded_available_layers.setSelectionMode(QListWidget.ExtendedSelection)
        self.excluded_layers = QListWidget()
        self.excluded_layers.setSelectionMode(QListWidget.ExtendedSelection)

        excl_btns = QVBoxLayout()
        btn_excl_add = QPushButton("Exclude >>")
        btn_excl_add.clicked.connect(self.cfg_exclude_layers)
        btn_excl_remove = QPushButton("<< Include")
        btn_excl_remove.clicked.connect(self.cfg_include_layers)
        excl_btns.addWidget(btn_excl_add)
        excl_btns.addWidget(btn_excl_remove)
        excl_btns.addStretch()

        excl_row.addWidget(QLabel("Available to Exclude"))
        excl_row.addWidget(self.excluded_available_layers, 1)
        excl_row.addLayout(excl_btns)
        excl_row.addWidget(QLabel("Excluded Layers (per Config)"))
        excl_row.addWidget(self.excluded_layers, 1)

        order_layout.addLayout(left_col, 1)
        order_layout.addLayout(mid_col)
        order_layout.addLayout(right_col, 1)

        wrapper = QVBoxLayout()
        wrapper.addLayout(order_layout)
        wrapper.addSpacing(8)
        wrapper.addLayout(excl_row)
        order_box.setLayout(wrapper)

        # --- Collection Metadata & Size ---
        meta_box = QGroupBox("Collection Metadata & Output Size")
        meta_layout = QHBoxLayout()

        left = QVBoxLayout()
        self.coll_name_input = QLineEdit()
        self.coll_desc_input = QTextEdit()
        left.addWidget(QLabel("Collection Name"))
        left.addWidget(self.coll_name_input)
        left.addWidget(QLabel("Description"))
        left.addWidget(self.coll_desc_input)

        right = QVBoxLayout()
        size_row = QHBoxLayout()
        self.size_w = QSpinBox(); self.size_w.setRange(64, 8192); self.size_w.setValue(980)
        self.size_h = QSpinBox(); self.size_h.setRange(64, 8192); self.size_h.setValue(1280)
        size_row.addWidget(QLabel("Width")); size_row.addWidget(self.size_w)
        size_row.addWidget(QLabel("Height")); size_row.addWidget(self.size_h)

        # Mapping sets attached to this config
        self.cfg_mapping_sets_list = QListWidget()
        self.cfg_mapping_sets_list.setSelectionMode(QListWidget.ExtendedSelection)
        btn_remove_ms = QPushButton("Remove Selected Mapping(s)")
        btn_remove_ms.clicked.connect(self.cfg_remove_mapping_sets)

        right.addWidget(QLabel("Output Size"))
        right.addLayout(size_row)
        right.addWidget(QLabel("Attached Mapping Sets"))
        right.addWidget(self.cfg_mapping_sets_list, 1)
        right.addWidget(btn_remove_ms)

        meta_layout.addLayout(left, 1)
        meta_layout.addLayout(right, 1)
        meta_box.setLayout(meta_layout)

        # --- Save / Load into editor ---
        actions_row = QHBoxLayout()
        btn_save = QPushButton("Save/Update Config")
        btn_save.clicked.connect(self.cfg_save_config)

        btn_load_into_editor = QPushButton("Load Existing Config Into Editor")
        btn_load_into_editor.clicked.connect(self.cfg_load_existing_into_editor)

        actions_row.addWidget(btn_save)
        actions_row.addWidget(btn_load_into_editor)
        actions_row.addStretch()

        layout.addLayout(name_row)
        layout.addWidget(dir_box)
        layout.addWidget(order_box)
        layout.addWidget(meta_box)
        layout.addLayout(actions_row)

        tab.setLayout(layout)
        return tab

    # --- Config Tab Actions ---
    def cfg_browse_layers_dir(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Layers Directory")
        if not folder:
            return
        self.cfg_layers_dir.setText(folder)
        self.cfg_reload_layers()

    def cfg_browse_output_dir(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Output Directory")
        if folder:
            self.cfg_output_dir.setText(folder)

    def cfg_reload_layers(self):
        self.available_layers.clear()
        self.layer_order.clear()
        self.excluded_available_layers.clear()
        self.excluded_layers.clear()

        layers_dir = self.cfg_layers_dir.text().strip()
        if not layers_dir or not os.path.isdir(layers_dir):
            QMessageBox.warning(self, "Error", "Please choose a valid Layers Dir.")
            return
        layers = [l for l in sorted(os.listdir(layers_dir)) if os.path.isdir(os.path.join(layers_dir, l))]
        for l in layers:
            self.available_layers.addItem(l)
            self.excluded_available_layers.addItem(l)

    def cfg_add_layers_to_order(self):
        for item in self.available_layers.selectedItems():
            existing = [self.layer_order.item(i).text() for i in range(self.layer_order.count())]
            if item.text() not in existing:
                self.layer_order.addItem(item.text())

    def cfg_remove_layers_from_order(self):
        for item in self.layer_order.selectedItems():
            self.layer_order.takeItem(self.layer_order.row(item))

    def cfg_move_layer_up(self):
        rows = sorted([self.layer_order.row(i) for i in self.layer_order.selectedItems()])
        for r in rows:
            if r <= 0:
                continue
            it = self.layer_order.takeItem(r)
            self.layer_order.insertItem(r - 1, it)
            self.layer_order.setCurrentItem(it)

    def cfg_move_layer_down(self):
        rows = sorted([self.layer_order.row(i) for i in self.layer_order.selectedItems()], reverse=True)
        for r in rows:
            if r >= self.layer_order.count() - 1:
                continue
            it = self.layer_order.takeItem(r)
            self.layer_order.insertItem(r + 1, it)
            self.layer_order.setCurrentItem(it)

    def cfg_exclude_layers(self):
        for it in self.excluded_available_layers.selectedItems():
            existing = [self.excluded_layers.item(i).text() for i in range(self.excluded_layers.count())]
            if it.text() not in existing:
                self.excluded_layers.addItem(it.text())

    def cfg_include_layers(self):
        for it in self.excluded_layers.selectedItems():
            self.excluded_layers.takeItem(self.excluded_layers.row(it))

    def cfg_collect_layer_order(self):
        return [self.layer_order.item(i).text() for i in range(self.layer_order.count())]

    def cfg_collect_excluded_layers(self):
        return [self.excluded_layers.item(i).text() for i in range(self.excluded_layers.count())]

    def cfg_collect_attached_mappings(self):
        return [self.cfg_mapping_sets_list.item(i).text() for i in range(self.cfg_mapping_sets_list.count())]

    def cfg_remove_mapping_sets(self):
        for it in self.cfg_mapping_sets_list.selectedItems():
            self.cfg_mapping_sets_list.takeItem(self.cfg_mapping_sets_list.row(it))

    def cfg_save_config(self):
        name = self.cfg_name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Error", "Please provide a Config Name.")
            return
        layers_dir = self.cfg_layers_dir.text().strip()
        output_dir = self.cfg_output_dir.text().strip()
        if not layers_dir or not os.path.isdir(layers_dir):
            QMessageBox.warning(self, "Error", "Invalid Layers Dir.")
            return
        if not output_dir:
            QMessageBox.warning(self, "Error", "Invalid Output Dir.")
            return

        layer_order = self.cfg_collect_layer_order()
        if not layer_order:
            # default to discovered sorted order
            for layer in sorted(os.listdir(layers_dir)):
                if os.path.isdir(os.path.join(layers_dir, layer)):
                    layer_order.append(layer)

        excluded_layers = self.cfg_collect_excluded_layers()

        config_obj = {
            "layers_dir": layers_dir,
            "output_dir": output_dir,
            "layer_order": layer_order,
            "excluded_layers": excluded_layers,         # NEW
            "mapping_sets": self.cfg_collect_attached_mappings(),
            "collection": {
                "name": self.coll_name_input.text().strip() or "Collection",
                "description": self.coll_desc_input.toPlainText().strip() or "",
            },
            "size": {"width": self.size_w.value(), "height": self.size_h.value()},
        }

        self.configs[name] = config_obj
        save_json(self.saved_configs_path, self.configs)
        self.active_config_name = name
        self.refresh_config_lists()
        QMessageBox.information(self, "Saved", f"Config '{name}' saved/updated.")

    def cfg_load_existing_into_editor(self):
        if not self.configs:
            QMessageBox.warning(self, "Error", "No saved configs.")
            return
        name = self.active_config_name or next(iter(self.configs.keys()))
        cfg = self.configs.get(name)
        if not cfg:
            QMessageBox.warning(self, "Error", "Active config not found.")
            return

        self.cfg_name_input.setText(name)
        self.cfg_layers_dir.setText(cfg.get("layers_dir", ""))
        self.cfg_output_dir.setText(cfg.get("output_dir", ""))
        self.coll_name_input.setText(cfg.get("collection", {}).get("name", ""))
        self.coll_desc_input.setText(cfg.get("collection", {}).get("description", ""))
        size = cfg.get("size", {})
        self.size_w.setValue(int(size.get("width", 980)))
        self.size_h.setValue(int(size.get("height", 1280)))

        # Reload lists
        self.cfg_reload_layers()
        # Order
        self.layer_order.clear()
        for layer in cfg.get("layer_order", []):
            self.layer_order.addItem(layer)
        # Excluded
        self.excluded_layers.clear()
        for layer in cfg.get("excluded_layers", []):
            self.excluded_layers.addItem(layer)
        # Mapping sets
        self.cfg_mapping_sets_list.clear()
        for ms in cfg.get("mapping_sets", []):
            self.cfg_mapping_sets_list.addItem(ms)

        QMessageBox.information(self, "Loaded", f"Loaded '{name}' into editor.")

    # =========================================================
    # TAB: Trait Mappings (with layer rarities + inclusion/exclusion pairs)
    # =========================================================
    def build_mappings_tab(self):
        tab = QWidget()
        layout = QVBoxLayout()

        # Top row: Set name + Source Config
        top_row = QHBoxLayout()
        self.map_set_name = QLineEdit()
        self.map_set_name.setPlaceholderText("Mapping set name...")
        self.map_source_config = QComboBox()
        self.map_source_config.currentIndexChanged.connect(self.map_reload_from_config)
        top_row.addWidget(QLabel("Mapping Set"))
        top_row.addWidget(self.map_set_name, 2)
        top_row.addWidget(QLabel("Source Config (loads its layers)"))
        top_row.addWidget(self.map_source_config, 2)

        # Layer rarities (folder-level)
        layer_box = QGroupBox("Layer (Folder) Rarities %")
        layer_layout = QVBoxLayout()
        self.layer_rarity_table = QTableWidget(0, 2)
        self.layer_rarity_table.setHorizontalHeaderLabels(["Layer", "Rarity %"])
        self.layer_rarity_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layer_layout.addWidget(self.layer_rarity_table)
        layer_box.setLayout(layer_layout)

        # Trait rarities
        trait_box = QGroupBox("Trait Rarities %")
        trait_layout = QVBoxLayout()
        self.map_trait_table = QTableWidget(0, 3)
        self.map_trait_table.setHorizontalHeaderLabels(["Layer", "Trait", "Rarity %"])
        self.map_trait_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        trait_layout.addWidget(self.map_trait_table)
        trait_box.setLayout(trait_layout)

        # Inclusion / Exclusion pairs
        pair_box = QGroupBox("Trait Mappings")
        pair_layout = QHBoxLayout()

        # Inclusion
        inc_col = QVBoxLayout()
        self.inc_a = QComboBox()
        self.inc_b = QComboBox()
        btn_add_inc = QPushButton("Add Inclusion (A ⇒ B)")
        btn_add_inc.clicked.connect(self.map_add_inclusion)
        self.inc_list = QListWidget()
        btn_remove_inc = QPushButton("Remove Selected Inclusion(s)")
        btn_remove_inc.clicked.connect(self.map_remove_inclusion)
        inc_col.addWidget(QLabel("Inclusion: pick A and B; A forces B"))
        inc_col.addWidget(self.inc_a)
        inc_col.addWidget(self.inc_b)
        inc_col.addWidget(btn_add_inc)
        inc_col.addWidget(self.inc_list, 1)
        inc_col.addWidget(btn_remove_inc)

        # Exclusion
        exc_col = QVBoxLayout()
        self.exc_a = QComboBox()
        self.exc_b = QComboBox()
        btn_add_exc = QPushButton("Add Exclusion (A ✕ B)")
        btn_add_exc.clicked.connect(self.map_add_exclusion)
        self.exc_list = QListWidget()
        btn_remove_exc = QPushButton("Remove Selected Exclusion(s)")
        btn_remove_exc.clicked.connect(self.map_remove_exclusion)
        exc_col.addWidget(QLabel("Exclusion: pick A and B; cannot co-occur"))
        exc_col.addWidget(self.exc_a)
        exc_col.addWidget(self.exc_b)
        exc_col.addWidget(btn_add_exc)
        exc_col.addWidget(self.exc_list, 1)
        exc_col.addWidget(btn_remove_exc)

        pair_layout.addLayout(inc_col, 1)
        pair_layout.addLayout(exc_col, 1)
        pair_box.setLayout(pair_layout)

        # Actions row
        actions = QHBoxLayout()
        btn_save_map = QPushButton("Save/Update Mapping Set")
        btn_save_map.clicked.connect(self.map_save_set)
        self.map_attach_target = QComboBox()
        btn_attach_map = QPushButton("Add Mapping to Config")
        btn_attach_map.clicked.connect(self.map_attach_to_config)
        actions.addWidget(btn_save_map)
        actions.addStretch()
        actions.addWidget(QLabel("Attach To Config"))
        actions.addWidget(self.map_attach_target)
        actions.addWidget(btn_attach_map)

        layout.addLayout(top_row)
        layout.addWidget(layer_box)
        layout.addWidget(trait_box)
        layout.addWidget(pair_box)
        layout.addLayout(actions)

        tab.setLayout(layout)
        return tab

    # --- Mappings Tab Actions ---
    def map_reload_from_config(self):
        # Clear tables/dropdowns
        self.layer_rarity_table.setRowCount(0)
        self.map_trait_table.setRowCount(0)
        self.rarity_spinboxes.clear()
        self.layer_rarity_spin.clear()
        for cb in (self.inc_a, self.inc_b, self.exc_a, self.exc_b):
            cb.clear()
        self.inc_list.clear()
        self.exc_list.clear()

        cfg_name = self.map_source_config.currentText().strip()
        cfg = self.configs.get(cfg_name)
        if not cfg:
            return
        layers_dir = cfg.get("layers_dir", "")
        if not layers_dir or not os.path.isdir(layers_dir):
            return

        # Load layers
        layers = [l for l in sorted(os.listdir(layers_dir)) if os.path.isdir(os.path.join(layers_dir, l))]

        # Layer rarities table
        for layer in layers:
            row = self.layer_rarity_table.rowCount()
            self.layer_rarity_table.insertRow(row)
            self.layer_rarity_table.setItem(row, 0, QTableWidgetItem(layer))
            sp = QSpinBox(); sp.setRange(0, 100); sp.setValue(100)
            self.layer_rarity_table.setCellWidget(row, 1, sp)
            self.layer_rarity_spin[layer] = sp

        # Traits table + pair dropdowns
        for layer in layers:
            lp = os.path.join(layers_dir, layer)
            files = [f for f in sorted(os.listdir(lp)) if f.lower().endswith(".png")]
            for f in files:
                trait = os.path.splitext(f)[0]
                key = f"{layer}:{trait}"
                r = self.map_trait_table.rowCount()
                self.map_trait_table.insertRow(r)
                self.map_trait_table.setItem(r, 0, QTableWidgetItem(layer))
                self.map_trait_table.setItem(r, 1, QTableWidgetItem(trait))
                sp = QSpinBox(); sp.setRange(0, 100); sp.setValue(100)
                self.map_trait_table.setCellWidget(r, 2, sp)
                self.rarity_spinboxes[key] = sp

                # for inclusion/exclusion dropdowns
                self.inc_a.addItem(key); self.inc_b.addItem(key)
                self.exc_a.addItem(key); self.exc_b.addItem(key)

        # If mapping set exists, preload values
        ms_name = self.map_set_name.text().strip()
        if ms_name and ms_name in self.mappings:
            ms = self.mappings[ms_name]
            # layer rarities
            for layer, v in (ms.get("layer_rarities", {}) or {}).items():
                sp = self.layer_rarity_spin.get(layer)
                if sp is not None:
                    try:
                        sp.setValue(int(v))
                    except Exception:
                        pass
            # trait rarities
            for k, v in (ms.get("rarities", {}) or {}).items():
                sp = self.rarity_spinboxes.get(k)
                if sp is not None:
                    try:
                        sp.setValue(int(v))
                    except Exception:
                        pass
            # inclusion/exclusion
            for a, b in (ms.get("include_pairs", []) or []):
                self.inc_list.addItem(f"{a} ⇒ {b}")
            for a, b in (ms.get("exclude_pairs", []) or []):
                self.exc_list.addItem(f"{a} ✕ {b}")

    def map_add_inclusion(self):
        a = self.inc_a.currentText().strip()
        b = self.inc_b.currentText().strip()
        if not a or not b or a == b:
            QMessageBox.warning(self, "Error", "Pick two different traits for inclusion.")
            return
        self.inc_list.addItem(f"{a} ⇒ {b}")

    def map_remove_inclusion(self):
        for it in self.inc_list.selectedItems():
            self.inc_list.takeItem(self.inc_list.row(it))

    def map_add_exclusion(self):
        a = self.exc_a.currentText().strip()
        b = self.exc_b.currentText().strip()
        if not a or not b or a == b:
            QMessageBox.warning(self, "Error", "Pick two different traits for exclusion.")
            return
        self.exc_list.addItem(f"{a} ✕ {b}")

    def map_remove_exclusion(self):
        for it in self.exc_list.selectedItems():
            self.exc_list.takeItem(self.exc_list.row(it))

    def map_save_set(self):
        name = self.map_set_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Error", "Provide a Mapping Set name.")
            return

        # Collect layer rarities
        layer_rarities = {}
        for layer, sp in self.layer_rarity_spin.items():
            layer_rarities[layer] = sp.value()

        # Collect trait rarities
        rarities = {}
        for key, sp in self.rarity_spinboxes.items():
            rarities[key] = sp.value()

        # Collect pairs
        include_pairs = []
        for i in range(self.inc_list.count()):
            txt = self.inc_list.item(i).text()
            if "⇒" in txt:
                a, b = txt.split("⇒")
                include_pairs.append([a.strip(), b.strip()])

        exclude_pairs = []
        for i in range(self.exc_list.count()):
            txt = self.exc_list.item(i).text()
            if "✕" in txt:
                a, b = txt.split("✕")
                exclude_pairs.append([a.strip(), b.strip()])

        self.mappings[name] = {
            "layer_rarities": layer_rarities,
            "rarities": rarities,
            "include_pairs": include_pairs,
            "exclude_pairs": exclude_pairs
        }
        save_json(self.saved_mappings_path, self.mappings)
        self.refresh_config_lists()
        QMessageBox.information(self, "Saved", f"Mapping Set '{name}' saved/updated.")

    def map_attach_to_config(self):
        ms_name = self.map_set_name.text().strip()
        if not ms_name:
            QMessageBox.warning(self, "Error", "Save or provide a Mapping Set name first.")
            return
        target_cfg = self.map_attach_target.currentText().strip()
        if not target_cfg or target_cfg not in self.configs:
            QMessageBox.warning(self, "Error", "Select a valid target Config.")
            return
        cfg = self.configs[target_cfg]
        ms_list = cfg.get("mapping_sets", [])
        if ms_name not in ms_list:
            ms_list.append(ms_name)
            cfg["mapping_sets"] = ms_list
            self.configs[target_cfg] = cfg
            save_json(self.saved_configs_path, self.configs)
            if self.active_config_name == target_cfg:
                self.cfg_mapping_sets_list.addItem(ms_name)
            QMessageBox.information(self, "Attached", f"'{ms_name}' added to config '{target_cfg}'.")
        else:
            QMessageBox.information(self, "Info", f"'{ms_name}' is already attached to '{target_cfg}'.")

    # =========================================================
    # TAB: Config Manager (+ Master Reset)
    # =========================================================
    def build_manager_tab(self):
        tab = QWidget()
        layout = QVBoxLayout()

        self.config_list = QListWidget()
        self.config_list.itemSelectionChanged.connect(self.on_manager_select)

        btn_reload = QPushButton("Reload Saved Configs & Mappings")
        btn_reload.clicked.connect(self.reload_from_disk)

        # Master reset
        reset_box = QGroupBox("Danger Zone")
        reset_layout = QHBoxLayout()
        btn_reset = QPushButton("MASTER RESET: Clear Logs, Configs, Mappings, and Generated Outputs")
        btn_reset.setStyleSheet("QPushButton { background: #a00; color: white; font-weight: bold; }")
        btn_reset.clicked.connect(self.master_reset)
        reset_layout.addWidget(btn_reset)
        reset_box.setLayout(reset_layout)

        layout.addWidget(QLabel("Saved Configurations"))
        layout.addWidget(self.config_list, 1)
        layout.addWidget(btn_reload)
        layout.addWidget(reset_box)
        tab.setLayout(layout)
        return tab

    def on_manager_select(self):
        it = self.config_list.currentItem()
        if it:
            self.active_config_name = it.text()

    def reload_from_disk(self):
        self.configs = load_json(self.saved_configs_path, {})
        self.mappings = load_json(self.saved_mappings_path, {})
        self.refresh_config_lists()
        QMessageBox.information(self, "Reloaded", "Configs and Mappings reloaded from disk.")

    def master_reset(self):
        reply = QMessageBox.question(
            self,
            "Confirm Master Reset",
            "This will CLEAR:\n\n• UI logs\n• All saved configs and mappings\n• All generated outputs in each config's output folder\n\nAre you absolutely sure?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        # 1) Clear UI logs
        if hasattr(self, "log_window"):
            self.log_window.clear()

        # 2) Delete config JSON files
        try:
            if os.path.isfile(self.saved_configs_path):
                os.remove(self.saved_configs_path)
            if os.path.isfile(self.saved_mappings_path):
                os.remove(self.saved_mappings_path)
        except Exception:
            pass

        # 3) Remove generated outputs for each known config
        for cfg in self.configs.values():
            out = cfg.get("output_dir")
            if out and os.path.isdir(out):
                for sub in ("images", "metadata"):
                    p = os.path.join(out, sub)
                    if os.path.isdir(p):
                        try:
                            shutil.rmtree(p)
                        except Exception:
                            pass

        # Reset in-memory
        self.configs = {}
        self.mappings = {}
        self.active_config_name = None
        self.refresh_config_lists()

        QMessageBox.information(self, "Reset Complete", "All configs, mappings, and generated outputs have been cleared.")

    def refresh_config_lists(self):
        # Manager list
        if hasattr(self, "config_list"):
            self.config_list.clear()
            for name in sorted(self.configs.keys()):
                self.config_list.addItem(name)
        # Generation list
        if hasattr(self, "gen_config_list"):
            self.gen_config_list.clear()
            for name in sorted(self.configs.keys()):
                self.gen_config_list.addItem(name)
        # Mappings tab: source config & attach target
        if hasattr(self, "map_source_config"):
            self.map_source_config.clear()
            for name in sorted(self.configs.keys()):
                self.map_source_config.addItem(name)
        if hasattr(self, "map_attach_target"):
            self.map_attach_target.clear()
            for name in sorted(self.configs.keys()):
                self.map_attach_target.addItem(name)

    # =========================================================
    # TAB: Generate NFTs (logging + stats)
    # =========================================================
    def build_generation_tab(self):
        tab = QWidget()
        layout = QVBoxLayout()

        self.gen_config_list = QListWidget()
        self.quantity_input = QSpinBox(); self.quantity_input.setRange(1, 999999); self.quantity_input.setValue(10)

        add_btn = QPushButton("Add Config to Queue (log only)")
        add_btn.clicked.connect(self.add_to_queue)

        self.log_window = QTextEdit(); self.log_window.setReadOnly(True)
        self.progress_bar = QProgressBar()
        self.stats_label = QLabel("Stats: waiting...")

        generate_btn = QPushButton("Start Generation")
        generate_btn.clicked.connect(self.start_generation)

        layout.addWidget(QLabel("Select Config for Generation"))
        layout.addWidget(self.gen_config_list)
        layout.addWidget(QLabel("Quantity"))
        layout.addWidget(self.quantity_input)
        layout.addWidget(add_btn)
        layout.addWidget(QLabel("Logs"))
        layout.addWidget(self.log_window, 1)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.stats_label)
        layout.addWidget(generate_btn)

        tab.setLayout(layout)
        return tab

    def add_to_queue(self):
        it = self.gen_config_list.currentItem()
        if not it:
            QMessageBox.warning(self, "Error", "Select a config first.")
            return
        name = it.text()
        qty = self.quantity_input.value()
        self.log_window.append(f"📝 Queued: {name} x{qty}")

    def log(self, msg):
        self.log_window.append(msg)

    def update_progress(self, done, total):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(done)

    def generation_done(self, stats):
        self.stats_label.setText(
            f"Stats: {stats['success']} success, {stats['duplicates']} duplicates, {stats['errors']} errors"
        )
        self.log("🎉 Generation complete.")

    def start_generation(self):
        it = self.gen_config_list.currentItem()
        if not it:
            QMessageBox.warning(self, "Error", "Select a config to generate.")
            return
        cfg_name = it.text()
        cfg = self.configs.get(cfg_name)
        if not cfg:
            QMessageBox.warning(self, "Error", "Config not found.")
            return
        qty = self.quantity_input.value()
        # Run in background thread
        self.worker = GenerationWorker(cfg, qty)
        self.worker.log_signal.connect(self.log)
        self.worker.progress_signal.connect(self.update_progress)
        self.worker.done_signal.connect(self.generation_done)
        self.worker.start()


# =========================================================
# Generation Logic
# =========================================================
def _safe_log(cb, msg):
    if cb:
        try:
            cb(msg)
        except Exception:
            pass


def _weighted_choice(options, weights):
    """
    options: list[str] trait names
    weights: list[int or float] same length
    Returns one element from options chosen by weights.
    If all weights are <= 0, falls back to uniform.
    """
    total = sum(w for w in weights if w > 0)
    if total <= 0:
        return random.choice(options) if options else None
    r = random.uniform(0, total)
    upto = 0.0
    for opt, w in zip(options, weights):
        if w <= 0:
            continue
        if upto + w >= r:
            return opt
        upto += w
    return options[-1] if options else None


def _collect_traits(layers_dir):
    """
    Return dict: { layer_name: [trait_name, ...] }
    Listing only .png files; trait_name is filename stem without extension.
    """
    out = {}
    if not os.path.isdir(layers_dir):
        return out
    for layer in sorted(os.listdir(layers_dir)):
        lp = os.path.join(layers_dir, layer)
        if not os.path.isdir(lp):
            continue
        traits = []
        for f in sorted(os.listdir(lp)):
            if f.lower().endswith(".png"):
                traits.append(os.path.splitext(f)[0])
        if traits:
            out[layer] = traits
    return out


def _merge_mapping_sets(config, log_callback=None):
    """
    Merge all selected mapping sets into a single ruleset.
    Later sets in config['mapping_sets'] override earlier rarities.

    Returns a dict:
      {
        "trait_rarities": { "Layer:Trait": int(0-100) },
        "layer_rarities": { "Layer": int(0-100) },
        "include_pairs": [ ["LayerA:TraitA", "LayerB:TraitB"], ... ],
        "exclude_pairs": [ ["LayerA:TraitA", "LayerB:TraitB"], ... ],
      }
    """
    trait_rarities = {}
    layer_rarities = {}
    include_pairs = []
    exclude_pairs = []

    mapping_sets = config.get("mapping_sets", []) or []
    mappings_path = os.path.join("configs", "saved_mappings.json")
    saved = {}
    if os.path.isfile(mappings_path):
        try:
            with open(mappings_path, "r") as f:
                saved = json.load(f)
        except Exception as e:
            _safe_log(log_callback, f"⚠️ Could not read saved_mappings.json: {e}")

    for name in mapping_sets:
        m = saved.get(name)
        if not m:
            _safe_log(log_callback, f"⚠️ Mapping set '{name}' not found.")
            continue

        # trait rarities
        for k, v in (m.get("rarities", {}) or {}).items():
            try:
                trait_rarities[k] = int(v)
            except Exception:
                pass

        # layer rarities
        for k, v in (m.get("layer_rarities", {}) or {}).items():
            try:
                layer_rarities[k] = int(v)
            except Exception:
                pass

        # include/exclude pairs
        for p in (m.get("include_pairs", []) or []):
            if isinstance(p, list) and len(p) == 2:
                include_pairs.append([p[0], p[1]])
        for p in (m.get("exclude_pairs", []) or []):
            if isinstance(p, list) and len(p) == 2:
                exclude_pairs.append([p[0], p[1]])

    return {
        "trait_rarities": trait_rarities,
        "layer_rarities": layer_rarities,
        "include_pairs": include_pairs,
        "exclude_pairs": exclude_pairs,
    }


def _is_excluded_by_pairs(candidate_key, selected_keys, exclude_pairs):
    """
    Return True if candidate_key conflicts with any selected_keys via exclude_pairs.
    """
    if not exclude_pairs:
        return False
    for sk in selected_keys:
        for a, b in exclude_pairs:
            if (candidate_key == a and sk == b) or (candidate_key == b and sk == a):
                return True
    return False


def run_generation(config, edition_size, log_callback=None, progress_callback=None):
    """
    Runs NFT generation with a given config.

    Config keys:
      layers_dir, output_dir
      layer_order: [layer_name, ...]
      excluded_layers: [layer_name, ...]
      mapping_sets: [mapping_set_name, ...]
      collection: { name, description }
      size: { width, height }
    """
    layers_dir = config["layers_dir"]
    output_dir = config["output_dir"]
    layer_order = config.get("layer_order", [])
    excluded_layers = set(config.get("excluded_layers", []) or [])
    collection = config.get("collection", {}) or {}
    size_conf = config.get("size", {}) or {}
    width = int(size_conf.get("width", 980))
    height = int(size_conf.get("height", 1280))

    images_dir = os.path.join(output_dir, "images")
    metadata_dir = os.path.join(output_dir, "metadata")
    os.makedirs(images_dir, exist_ok=True)
    os.makedirs(metadata_dir, exist_ok=True)

    # Merge all mapping set rules
    rules = _merge_mapping_sets(config, log_callback=log_callback)
    trait_rarities = rules["trait_rarities"]
    layer_rarities = rules["layer_rarities"]
    include_pairs = rules["include_pairs"]
    exclude_pairs = rules["exclude_pairs"]

    # Discover filesystem traits
    all_traits = _collect_traits(layers_dir)

    # Default layer order if not provided
    if not layer_order:
        layer_order = sorted(all_traits.keys())

    # Remove excluded layers from consideration
    final_layer_order = [L for L in layer_order if L in all_traits and L not in excluded_layers]

    generated_dna = set()
    stats = {"success": 0, "duplicates": 0, "errors": 0}

    for edition_number in range(1, edition_size + 1):
        try:
            canvas_size = (width, height)
            result_image = Image.new("RGBA", canvas_size)

            selected = {}            # layer -> trait
            selected_keys = []       # ["Layer:Trait", ...] for quick conflict checks
            forced_selection = {}    # layer -> trait (caused by include mappings)

            # 1) Walk layers in order selecting traits
            for layer in final_layer_order:
                options = all_traits.get(layer, [])
                if not options:
                    continue

                # Apply layer rarity (chance to skip a layer)
                layer_p = int(layer_rarities.get(layer, 100))
                must_include = layer in forced_selection  # inclusion map can force presence
                if not must_include and random.random() > (layer_p / 100.0):
                    # skip this layer entirely
                    continue

                # Forced selection from inclusion pairs?
                chosen_trait = forced_selection.get(layer)

                if chosen_trait is None:
                    # If any selected trait requires an inclusion for THIS layer,
                    # we restrict to the required trait (only mapping is used).
                    required_trait_for_layer = None
                    for a, b in include_pairs:
                        # a requires b
                        try:
                            la, ta = a.split(":", 1)
                            lb, tb = b.split(":", 1)
                        except ValueError:
                            continue
                        if f"{la}:{ta}" in selected_keys and lb == layer:
                            required_trait_for_layer = tb
                            break

                    if required_trait_for_layer is not None:
                        if required_trait_for_layer in options:
                            chosen_trait = required_trait_for_layer
                        else:
                            _safe_log(
                                log_callback,
                                f"⚠️ Inclusion requires '{layer}:{required_trait_for_layer}', but not found; skipping layer."
                            )
                            # If mapping says only the mapped trait should be used, and it's missing, skip layer.
                            continue

                if chosen_trait is None:
                    # Weighted choice by trait rarities, minus excluded by pairs with already selected traits.
                    viable_opts = []
                    viable_wts = []
                    for t in options:
                        key = f"{layer}:{t}"
                        if _is_excluded_by_pairs(key, selected_keys, exclude_pairs):
                            continue
                        weight = int(trait_rarities.get(key, 100))
                        if weight < 0:
                            weight = 0
                        viable_opts.append(t)
                        viable_wts.append(weight)

                    if not viable_opts:
                        # nothing compatible, skip layer
                        continue

                    chosen_trait = _weighted_choice(viable_opts, viable_wts)
                    if chosen_trait is None:
                        continue

                # Register selection
                selected[layer] = chosen_trait
                key = f"{layer}:{chosen_trait}"
                selected_keys.append(key)

                # Handle inclusion chains: if selected key 'a' requires 'b', force it
                for a, b in include_pairs:
                    if key == a:
                        try:
                            lb, tb = b.split(":", 1)
                        except ValueError:
                            continue
                        # Only set forced if target layer hasn't been processed yet
                        if lb not in selected:
                            forced_selection[lb] = tb

            # 2) DNA and duplicate check
            dna_parts = []
            for layer in final_layer_order:
                trait = selected.get(layer, "__none__")
                dna_parts.append(f"{layer}:{trait}")
            dna = "|".join(dna_parts)

            if dna in generated_dna:
                stats["duplicates"] += 1
                _safe_log(log_callback, f"❌ Duplicate at #{edition_number}, skipping.")
                if progress_callback:
                    progress_callback(edition_number, edition_size)
                continue

            # 3) Composite image
            for layer in final_layer_order:
                trait = selected.get(layer)
                if not trait or trait == "__none__":
                    continue
                layer_path = os.path.join(layers_dir, layer)
                img_path = os.path.join(layer_path, f"{trait}.png")
                if not os.path.isfile(img_path):
                    # try case-insensitive match
                    files = [f for f in os.listdir(layer_path) if f.lower().endswith(".png")]
                    match = next((f for f in files if os.path.splitext(f)[0].lower() == trait.lower()), None)
                    if match:
                        img_path = os.path.join(layer_path, match)
                    else:
                        _safe_log(log_callback, f"⚠️ Missing image for '{layer}:{trait}'")
                        continue
                try:
                    layer_img = Image.open(img_path).convert("RGBA")
                except Exception as e:
                    _safe_log(log_callback, f"⚠️ Error loading '{img_path}': {e}")
                    continue
                if layer_img.size != canvas_size:
                    layer_img = layer_img.resize(canvas_size, RESAMPLE_LANCZOS)
                result_image = Image.alpha_composite(result_image, layer_img)

            # 4) Save output
            generated_dna.add(dna)
            file_name = f"{edition_number}.png"
            result_image.save(os.path.join(images_dir, file_name))

            attributes = []
            for layer in final_layer_order:
                trait = selected.get(layer)
                if trait and trait != "__none__":
                    attributes.append({"trait_type": layer, "value": trait})

            coll_name = collection.get("name", "Collection")
            description = collection.get("description", "")
            metadata = {
                "name": f"{coll_name} #{edition_number}",
                "description": description,
                "image": file_name,
                "attributes": attributes,
                "edition": edition_number,
            }
            with open(os.path.join(metadata_dir, f"{edition_number}.json"), "w") as mf:
                json.dump(metadata, mf, indent=4)

            stats["success"] += 1
            _safe_log(log_callback, f"✅ Generated #{edition_number}")

        except Exception as e:
            stats["errors"] += 1
            _safe_log(log_callback, f"⚠️ Error on #{edition_number}: {e}")

        if progress_callback:
            progress_callback(edition_number, edition_size)

    return stats


# =========================================================
# Entry point
# =========================================================
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = NFTGeneratorGUI()
    window.show()
    sys.exit(app.exec())
