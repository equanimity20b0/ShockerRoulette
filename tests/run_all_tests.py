import subprocess
import sys
import os
import glob

def run_tests():
    print("==================================================")
    print(" Running Server Python Unit Tests")
    print("==================================================")
    cmd_py = [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py"]
    res_py = subprocess.run(cmd_py)

    print("\n==================================================")
    print(" Running Web Client JavaScript Unit Tests")
    print("==================================================")
    js_test_files = glob.glob(os.path.join("tests", "test_*.js")) + glob.glob(os.path.join("tests", "*.test.js"))
    if not js_test_files:
        print("No JavaScript test files found in tests/")
        res_js_code = 0
    else:
        print(f"Discovered JavaScript test files: {js_test_files}")
        cmd_js = ["node", "--test"] + js_test_files
        res_js = subprocess.run(cmd_js)
        res_js_code = res_js.returncode

    if res_py.returncode == 0 and res_js_code == 0:
        print("\nAll server and web client unit tests PASSED successfully!")
        sys.exit(0)
    else:
        print("\nSome unit tests FAILED.")
        sys.exit(1)

if __name__ == "__main__":
    run_tests()
