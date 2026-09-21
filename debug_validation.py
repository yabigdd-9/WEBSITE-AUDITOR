#!/usr/bin/env python3
"""
Debug the validation issue
"""

def debug_validation():
    with open("/Users/dd/Downloads/WEBSITE-AUDITOR-master/auditor_toolkit/evidence_brief.py", 'r') as f:
        content = f.read()

    print("File content length:", len(content))
    print("First 200 chars:", repr(content[:200]))

    # Check for the exact strings
    to_dict_str = "def to_dict(self) -> Dict[str, Any]:"
    from_dict_str = "    @classmethod\n    def from_dict(cls, data: Dict[str, Any]) -> \"EvidenceBrief\":"

    print("\nSearching for:")
    print("to_dict:", repr(to_dict_str))
    print("from_dict:", repr(from_dict_str))

    print("\nResults:")
    print("to_dict found:", to_dict_str in content)
    print("from_dict found:", from_dict_str in content)

    # Let's look at the actual content around where these should be
    lines = content.split('\n')
    for i, line in enumerate(lines):
        if 'to_dict' in line:
            print(f"Line {i}: {repr(line)}")
            # Print surrounding lines
            for j in range(max(0, i-2), min(len(lines), i+3)):
                marker = ">>> " if j == i else "    "
                print(f"{marker}{j}: {repr(lines[j])}")
            break

    print("\n" + "="*50)
    for i, line in enumerate(lines):
        if 'from_dict' in line:
            print(f"Line {i}: {repr(line)}")
            # Print surrounding lines
            for j in range(max(0, i-2), min(len(lines), i+3)):
                marker = ">>> " if j == i else "    "
                print(f"{marker}{j}: {repr(lines[j])}")
            break

if __name__ == "__main__":
    debug_validation()