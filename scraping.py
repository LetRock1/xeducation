import os

# Scan the folder where this script exists (portable)
ROOT_FOLDER = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE = "new.txt"

# Folders we NEVER want in snapshots
SKIP_DIRS = {
    ".git",
    ".venv", "venv", "env",
    "__pycache__",
    "node_modules",
    ".idea", ".vscode",
    "dist", "build",
    "site-packages",
    ".next", ".nuxt",
    "coverage", ".pytest_cache"
}

# Prevent recursive snapshot growth
IGNORE_FILES = {"new.txt", "final.txt"}

# Allowed source file types
ALLOWED_EXTENSIONS = {
    ".py",".js",".ts",".jsx",".tsx",
    ".html",".css",".json",".md",".txt",
    ".yml",".yaml",".env"
}

# Skip huge files (important for real projects)
MAX_FILE_SIZE_MB = 2
MAX_FILE_SIZE = MAX_FILE_SIZE_MB * 1024 * 1024


# ─────────────────────────────────────────────
# Build folder tree
# ─────────────────────────────────────────────
def build_tree(start_path):
    tree_lines = []

    for root, dirs, files in os.walk(start_path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]

        level = root.replace(start_path, "").count(os.sep)
        indent = "│   " * level
        folder_name = os.path.basename(root)

        if level == 0:
            tree_lines.append(folder_name)
        else:
            tree_lines.append(f"{indent}├── {folder_name}")

        sub_indent = "│   " * (level + 1)

        for f in files:
            if f in IGNORE_FILES:
                continue
            if os.path.splitext(f)[1].lower() in ALLOWED_EXTENSIONS:
                tree_lines.append(f"{sub_indent}└── {f}")

    return "\n".join(tree_lines)


# ─────────────────────────────────────────────
# Dump file contents
# ─────────────────────────────────────────────
def dump_files(outfile):
    for root, dirs, files in os.walk(ROOT_FOLDER):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]

        for file in files:
            if file in IGNORE_FILES:
                continue
            if os.path.splitext(file)[1].lower() not in ALLOWED_EXTENSIONS:
                continue

            full_path = os.path.join(root, file)

            # Skip huge files
            if os.path.getsize(full_path) > MAX_FILE_SIZE:
                continue

            try:
                with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()

                outfile.write("\n\n")
                outfile.write("=" * 90 + "\n")
                outfile.write(f"FILE: {full_path}\n")
                outfile.write("=" * 90 + "\n\n")
                outfile.write(content)

            except Exception as e:
                outfile.write("\n\n")
                outfile.write("=" * 90 + "\n")
                outfile.write(f"FILE: {full_path} (Could not read)\n")
                outfile.write(f"ERROR: {str(e)}\n")
                outfile.write("=" * 90 + "\n")


# ─────────────────────────────────────────────
# Main runner
# ─────────────────────────────────────────────
def create_snapshot():
    with open(OUTPUT_FILE, "w", encoding="utf-8") as outfile:

        outfile.write("ALL PROJECT FILES SNAPSHOT\n")
        outfile.write("=" * 90 + "\n\n")

        outfile.write("PROJECT STRUCTURE\n")
        outfile.write("=" * 90 + "\n\n")
        outfile.write(build_tree(ROOT_FOLDER))

        outfile.write("\n\n\nPROJECT FILE CONTENTS\n")
        outfile.write("=" * 90 + "\n")

        dump_files(outfile)

    print(f"\n✅ Snapshot created successfully → {OUTPUT_FILE}")


if __name__ == "__main__":
    create_snapshot()