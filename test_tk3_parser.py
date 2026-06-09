import sys
from pathlib import Path
from combine_tk3 import load_tk3_file_any_columns, N_COLS

def test_file(path: Path):
    print(f"\n=== Testing {path.name} ===")

    if not path.exists():
        print(f"❌ File not found: {path}")
        return False

    try:
        df = load_tk3_file_any_columns(path)
    except Exception as e:
        print(f"❌ Parsing failed: {e}")
        return False

    if df.shape[1] != N_COLS:
        print(f"❌ Column mismatch: {df.shape[1]} (expected {N_COLS})")
        return False

    print(f"✓ OK — {len(df)} rows, {df.shape[1]} columns")
    return True


def main():
    folder = Path(sys.argv[1])

    print("\n========== TK3 PARSER TESTSUITE ==========")

    test_files = [
        "WASC3_result_2020072.csv",
        "WASC3_result_2020194.csv"
    ]

    for f in test_files:
        test_file(folder / f)

    print("\n==========================================")

if __name__ == "__main__":
    main()
