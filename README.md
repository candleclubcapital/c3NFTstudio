
<img width="1350" height="919" alt="Screenshot 2025-10-01 at 5 04 46 AM" src="https://github.com/user-attachments/assets/8babb4a0-f29c-43e2-94ff-3f6c32668521" />

<img width="1349" height="919" alt="Screenshot 2025-10-01 at 5 04 54 AM" src="https://github.com/user-attachments/assets/505bb857-9508-4790-9b5d-e4c80987bf44" />

# C3 NFT Studio

**C3 NFT Studio** is a full-featured **desktop application for NFT collection generation**.
It provides a clean GUI (built with PySide6 / Qt) that allows you to:

* Manage multiple **configs** with ordered layer structures
* Define **trait rarities, layer rarities, and mapping rules**
* Apply **inclusion/exclusion constraints** (e.g., “if hat=red, shirt=blue is forbidden”)
* Preview and generate thousands of unique NFTs with **automatic duplicate detection**
* Save both **image composites** and **metadata JSON files** (ready for IPFS/marketplace uploads)
* Easily manage configs, mapping sets, and outputs through one streamlined interface

Everything is contained in a single Python file (`nft_studio.py`) for easy use.

---

## ✨ Features

* **GUI Layer Config Builder**

  * Select layer directories, order them, exclude certain folders
  * Define output size and collection metadata

* **Trait & Layer Mapping Editor**

  * Set rarities (%) at both the **layer** and **trait** level
  * Define **inclusion pairs** (A ⇒ B) and **exclusion pairs** (A ✕ B)

* **Config Manager**

  * Save and load multiple configs
  * Attach mapping sets to configs
  * Full reset option (danger zone)

* **NFT Generator**

  * Background thread generation with logs and progress bar
  * Stats summary (success, duplicates, errors)
  * Outputs PNG images and JSON metadata

---

## 🖼️ Example Workflow

1. **Prepare Layers**

   * Each folder = one trait category (e.g., `Background/`, `Body/`, `Head/`, `Hat/`)
   * Each `.png` inside = a trait (transparent background recommended)

   Example:

   ```
   layers/
     Background/
       Blue.png
       Red.png
     Body/
       Normal.png
       Zombie.png
     Hat/
       Cap.png
       Crown.png
   ```

2. **Open the App**

   ```
   python c3nft.py
   ```

3. **Create a Config**

   * Point to the `layers/` directory
   * Choose an output directory
   * Arrange layer order
   * Save config

4. **Add a Mapping Set**

   * Pick rarities for layers/traits
   * Define inclusions/exclusions
   * Save & attach to config

5. **Generate NFTs**

   * Select config, set quantity
   * Click **Start Generation**
   * Watch progress + logs in real-time

6. **Outputs**

   * Images saved in: `<output_dir>/images/`
   * Metadata saved in: `<output_dir>/metadata/`

---

## 🚀 Installation


1. Run:

   ```bash
   python c3nft.py
   ```

---

## ⚠️ Notes

* Only `.png` files are supported for traits
* Output images are automatically resized to match your configured width/height
* Duplicate DNAs are skipped, ensuring unique NFTs
* Excluded layers & trait rules are respected during generation

---
