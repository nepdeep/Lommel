import os
import glob
import shutil
import re

BACKUP_DIR = "backup"
SELF_NAMES = {
    "backup.py",
    "bkup_html.py",
    "bkup_python.py",
    "bkup_combined.py",
}


def ensure_backup_directory():
    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR)
        print(f"Created backup directory: {BACKUP_DIR}")


def sanitize_filename(text):
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        text = text.replace(char, "_")
    text = " ".join(text.split())
    return text[:50]


def get_next_backup_number(base_filename):
    revision = 1
    while True:
        pattern = os.path.join(BACKUP_DIR, f"{base_filename}R{revision:02d}.*")
        existing_files = glob.glob(pattern)
        if not existing_files:
            return revision
        revision += 1


def detect_available_file_types():
    html_files = sorted(glob.glob("*.html"))
    py_files = sorted(
        f for f in glob.glob("*.py")
        if os.path.basename(f).lower() not in SELF_NAMES
    )
    return html_files, py_files


def choose_filetype_first():
    while True:
        html_files, py_files = detect_available_file_types()
        has_html = len(html_files) > 0
        has_py = len(py_files) > 0

        if not has_html and not has_py:
            print("No HTML or Python files found.")
            return None, [], []

        if has_html and has_py:
            print("\n" + "=" * 55)
            print("Choose File Type")
            print("=" * 55)
            print("1 / H = HTML")
            print("2 / P = Python")
            print("3 / B = Both")
            print("Q = Quit")
            print("-" * 55)

            choice = input("Select file type: ").strip().upper()

            if choice in ("1", "H"):
                return "html", html_files, py_files
            elif choice in ("2", "P"):
                return "py", html_files, py_files
            elif choice in ("3", "B"):
                return "both", html_files, py_files
            elif choice == "Q":
                return None, [], []
            else:
                print("Invalid choice. Please try again.")
                continue

        if has_html:
            print("\nOnly HTML files found. Going directly to HTML mode.")
            return "html", html_files, py_files

        if has_py:
            print("\nOnly Python files found. Going directly to Python mode.")
            return "py", html_files, py_files


def backup_files(files, label):
    ensure_backup_directory()

    if not files:
        print(f"No {label} files found to backup.")
        return

    print(f"\nFound {len(files)} {label} file(s) to backup:")
    print("For each file, enter a short description.\n")

    for source_file in files:
        print(f"Backing up: {source_file}")
        base_name = os.path.splitext(source_file)[0]
        revision_num = get_next_backup_number(base_name)

        while True:
            description = input(
                f"Enter short description for {source_file} R{revision_num:02d}: "
            ).strip()
            if description:
                break
            print("Description cannot be empty.")

        clean_description = sanitize_filename(description)
        backup_filename = f"{base_name}R{revision_num:02d}.backup.{clean_description}"
        backup_filepath = os.path.join(BACKUP_DIR, backup_filename)

        try:
            shutil.copy2(source_file, backup_filepath)
            print(f"  ✓ Created: {backup_filepath}\n")
        except Exception as e:
            print(f"  ✗ Error backing up {source_file}: {e}\n")

    print(f"{label} backup process completed!")


def detect_original_extension(base_name, current_html_bases=None, current_py_bases=None):
    if current_html_bases is None or current_py_bases is None:
        html_files, py_files = detect_available_file_types()
        current_html_bases = {os.path.splitext(f)[0] for f in html_files}
        current_py_bases = {os.path.splitext(f)[0] for f in py_files}

    if base_name in current_html_bases:
        return ".html"
    if base_name in current_py_bases:
        return ".py"
    return None


def get_backup_files(selected_type=None):
    backup_files = {}

    if not os.path.exists(BACKUP_DIR):
        return backup_files

    pattern = r"^(.+)R(\d+)\.backup\.(.+)$"

    current_html_files, current_py_files = detect_available_file_types()
    current_html_bases = {os.path.splitext(f)[0] for f in current_html_files}
    current_py_bases = {os.path.splitext(f)[0] for f in current_py_files}

    for file in os.listdir(BACKUP_DIR):
        match = re.match(pattern, file)
        if not match:
            continue

        base_name = match.group(1)
        revision = int(match.group(2))
        description = match.group(3)

        ext = detect_original_extension(base_name, current_html_bases, current_py_bases)
        if ext is None:
            ext = "unknown"

        if selected_type == "html" and ext not in [".html", "unknown"]:
            continue
        if selected_type == "py" and ext not in [".py", "unknown"]:
            continue

        if base_name not in backup_files:
            backup_files[base_name] = {
                "extension": ext,
                "revisions": []
            }

        backup_files[base_name]["revisions"].append({
            "revision": revision,
            "description": description,
            "filename": file
        })

    for base_name in backup_files:
        backup_files[base_name]["revisions"].sort(key=lambda x: x["revision"])

    return backup_files


def ask_restore_extension(base_name, selected_type):
    if selected_type == "html":
        return ".html"
    if selected_type == "py":
        return ".py"

    while True:
        ext_choice = input(
            f"Restore '{base_name}' as (.html/.py) [H/P]: "
        ).strip().upper()

        if ext_choice in (".HTML", "HTML", "H"):
            return ".html"
        elif ext_choice in (".PY", "PY", "P"):
            return ".py"
        else:
            print("Please enter H or P.")


def restore_files(selected_type):
    backup_data = get_backup_files(selected_type=selected_type)

    if not backup_data:
        print("No matching backup files found in the backup directory.")
        return

    print("\nAvailable backup files:")
    print("=" * 70)

    file_options = []
    option_num = 1

    for base_name, data in sorted(backup_data.items()):
        ext = data["extension"]
        display_ext = "" if ext == "unknown" else ext

        print(f"\n{base_name}{display_ext}:")
        for backup in data["revisions"]:
            print(f"  {option_num}. R{backup['revision']:02d} - {backup['description']}")
            file_options.append({
                "base_name": base_name,
                "extension": data["extension"],
                "backup_info": backup
            })
            option_num += 1

    print("\n" + "=" * 70)

    while True:
        choice = input(
            f"Select file to restore (1-{len(file_options)}) or Q to quit: "
        ).strip()

        if choice.upper() == "Q":
            return

        try:
            choice_num = int(choice)
            if 1 <= choice_num <= len(file_options):
                break
            print(f"Please enter a number between 1 and {len(file_options)}")
        except ValueError:
            print("Please enter a valid number.")

    selected = file_options[choice_num - 1]
    base_name = selected["base_name"]
    ext = selected["extension"]
    backup_info = selected["backup_info"]

    if ext == "unknown" or not ext:
        ext = ask_restore_extension(base_name, selected_type)

    backup_filename = backup_info["filename"]
    backup_filepath = os.path.join(BACKUP_DIR, backup_filename)
    target_filename = f"{base_name}{ext}"

    print(f"\nRestore '{backup_filename}' to '{target_filename}'?")
    confirm = input("This will overwrite the current file. Continue? (y/N): ").strip().lower()

    if confirm not in ("y", "yes"):
        print("Restore cancelled.")
        return

    try:
        if os.path.exists(target_filename):
            safety_backup = f"{target_filename}.before_restore"
            shutil.copy2(target_filename, safety_backup)
            print(f"  ✓ Created safety backup: {safety_backup}")

        shutil.copy2(backup_filepath, target_filename)
        print(f"  ✓ Restored: {target_filename}")
        print(f"  ✓ From: {backup_filepath}")

    except Exception as e:
        print(f"  ✗ Error restoring file: {e}")


def backup_restore_menu(selected_type, html_files, py_files):
    while True:
        print("\n" + "=" * 55)
        if selected_type == "html":
            print("HTML Backup Options")
        elif selected_type == "py":
            print("Python Backup Options")
        else:
            print("HTML + Python Backup Options")
        print("=" * 55)
        print("1 / B = Backup")
        print("2 / R = Restore")
        print("3 / C = Change File Type")
        print("4 / Q = Quit")
        print("-" * 55)

        choice = input("Enter your choice: ").strip().upper()

        if choice in ("1", "B"):
            if selected_type == "html":
                backup_files(html_files, "HTML")
            elif selected_type == "py":
                backup_files(py_files, "Python")
            elif selected_type == "both":
                backup_files(html_files, "HTML")
                backup_files(py_files, "Python")
        elif choice in ("2", "R"):
            restore_files(selected_type)
        elif choice in ("3", "C"):
            return "change"
        elif choice in ("4", "Q"):
            return "quit"
        else:
            print("Invalid choice. Please try again.")


def main():
    while True:
        selected_type, html_files, py_files = choose_filetype_first()

        if selected_type is None:
            print("Goodbye!")
            break

        result = backup_restore_menu(selected_type, html_files, py_files)

        if result == "quit":
            print("Goodbye!")
            break
        elif result == "change":
            continue


if __name__ == "__main__":
    main()