#!/usr/bin/env python3
"""
Tests for the cleanup skill.

Run with: python3 test_cleanup.py
"""

import os
import sys
import json
import tempfile
import shutil
import subprocess
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cleanup


class TestCleanup:
    """Test cases for cleanup.py"""
    
    def __init__(self):
        self.temp_dir = None
        self.passed = 0
        self.failed = 0
    
    def setup(self):
        """Create a temporary directory for testing"""
        self.temp_dir = tempfile.mkdtemp()
        os.chdir(self.temp_dir)
        
        # Initialize git repo
        subprocess.run(["git", "init"], capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test User"], capture_output=True)
    
    def teardown(self):
        """Clean up temporary directory"""
        if self.temp_dir and os.path.exists(self.temp_dir):
            os.chdir("/")
            shutil.rmtree(self.temp_dir)
    
    def assert_equal(self, actual, expected, message=""):
        """Assert that two values are equal"""
        if actual == expected:
            self.passed += 1
            return True
        else:
            self.failed += 1
            print(f"FAIL: {message}")
            print(f"  Expected: {expected}")
            print(f"  Actual: {actual}")
            return False
    
    def assert_true(self, condition, message=""):
        """Assert that a condition is true"""
        if condition:
            self.passed += 1
            return True
        else:
            self.failed += 1
            print(f"FAIL: {message}")
            return False
    
    def assert_in(self, item, container, message=""):
        """Assert that item is in container"""
        if item in container:
            self.passed += 1
            return True
        else:
            self.failed += 1
            print(f"FAIL: {message}")
            print(f"  Expected {item} in {container}")
            return False
    
    def test_junk_file_detection(self):
        """Test that junk files are correctly identified"""
        print("\nTesting junk file detection...")
        
        junk_files = [
            "test.log",
            "temp.tmp",
            "file~",
            ".DS_Store",
            "Thumbs.db",
            "test.swp",
            "test.pyc",
            "test.bak",
        ]
        
        for filename in junk_files:
            result = cleanup.is_junk_file(filename)
            self.assert_true(result, f"Should identify {filename} as junk")
    
    def test_non_junk_file_detection(self):
        """Test that non-junk files are correctly identified"""
        print("\nTesting non-junk file detection...")
        
        non_junk_files = [
            "README.md",
            "main.py",
            "index.ts",
            "package.json",
            "test.py",
        ]
        
        for filename in non_junk_files:
            result = cleanup.is_junk_file(filename)
            self.assert_true(not result, f"Should NOT identify {filename} as junk")
    
    def test_read_file_content(self):
        """Test reading file content"""
        print("\nTesting read_file_content...")
        
        test_file = "test.txt"
        test_content = "Hello, World!"
        
        with open(test_file, "w") as f:
            f.write(test_content)
        
        content = cleanup.read_file_content(test_file)
        self.assert_equal(content, test_content, "File content should match")
    
    def test_get_git_status_empty(self):
        """Test git status on clean repo"""
        print("\nTesting get_git_status on clean repo...")
        
        # Clean up any test files created by previous tests
        if os.path.exists("test.txt"):
            os.remove("test.txt")
        
        status = cleanup.get_git_status()
        self.assert_equal(status, [], "Clean repo should have no status")
    
    def test_get_git_status_with_changes(self):
        """Test git status with uncommitted changes"""
        print("\nTesting get_git_status with changes...")
        
        # Create and commit a file
        with open("initial.txt", "w") as f:
            f.write("initial")
        subprocess.run(["git", "add", "initial.txt"], capture_output=True)
        subprocess.run(["git", "commit", "-m", "initial"], capture_output=True)
        
        # Modify the file
        with open("initial.txt", "w") as f:
            f.write("modified")
        
        status = cleanup.get_git_status()
        self.assert_true(len(status) > 0, "Modified file should show in status")
    
    def test_get_untracked_files(self):
        """Test getting untracked files"""
        print("\nTesting get_untracked_files...")
        
        # Create untracked files
        with open("untracked1.txt", "w") as f:
            f.write("untracked")
        with open("untracked2.txt", "w") as f:
            f.write("untracked")
        
        untracked = cleanup.get_untracked_files()
        self.assert_true(len(untracked) >= 2, "Should find untracked files")
        self.assert_in("untracked1.txt", untracked, "Should find untracked1.txt")
    
    def test_get_all_tracked_files(self):
        """Test getting all tracked files"""
        print("\nTesting get_all_tracked_files...")
        
        # Create and commit a file
        with open("tracked.txt", "w") as f:
            f.write("tracked")
        subprocess.run(["git", "add", "tracked.txt"], capture_output=True)
        subprocess.run(["git", "commit", "-m", "add tracked"], capture_output=True)
        
        tracked = cleanup.get_all_tracked_files()
        self.assert_in("tracked.txt", tracked, "Should find tracked.txt")
    
    def test_generate_cleanup_plan(self):
        """Test generating cleanup plan"""
        print("\nTesting generate_cleanup_plan...")
        
        findings = {
            "uncommitted_changes": ["M modified.txt"],
            "untracked_files": ["junk.log", "important.txt"],
            "dead_files": [
                {"path": "old.py", "status": "unreferenced", "reason": "No references found"}
            ],
            "outdated_docs": [
                {"path": "old.md", "status": "stale", "reason": "Not modified in 400 days"}
            ]
        }
        
        plan = cleanup.generate_cleanup_plan(findings)
        
        self.assert_in("# Cleanup Plan", plan, "Plan should have header")
        self.assert_in("Uncommitted Changes", plan, "Plan should have uncommitted changes section")
        self.assert_in("Untracked Files", plan, "Plan should have untracked files section")
        self.assert_in("Potentially Dead Files", plan, "Plan should have dead files section")
        self.assert_in("junk.log", plan, "Plan should mention junk.log")
    
    def test_find_file_references(self):
        """Test finding file references"""
        print("\nTesting find_file_references...")
        
        # Create a source file that references another file
        with open("main.py", "w") as f:
            f.write("import utils\nfrom utils import helper\n")
        
        # Create the referenced file
        with open("utils.py", "w") as f:
            f.write("def helper(): pass\n")
        
        # Find references to utils.py
        references = cleanup.find_file_references("utils.py", ["."])
        
        self.assert_true(len(references) > 0, "Should find references to utils.py")
        # The reference may be "main.py" or "./main.py" depending on the path
        has_main_py = any("main.py" in ref for ref in references)
        self.assert_true(has_main_py, "main.py should reference utils.py")
    
    def test_log_cleanup(self):
        """Test logging cleanup actions"""
        print("\nTesting log_cleanup...")
        
        findings = {
            "uncommitted_changes": [],
            "untracked_files": ["junk.log"],
            "dead_files": [],
            "outdated_docs": []
        }
        
        actions_taken = ["Removed file: junk.log"]
        
        cleanup.log_cleanup(findings, actions_taken)
        
        log_file = Path("local/CLEANUP_LOG.md")
        self.assert_true(log_file.exists(), "Log file should be created")
        
        content = log_file.read_text()
        self.assert_in("Cleanup Log", content, "Log should have header")
        self.assert_in("junk.log", content, "Log should mention junk.log")
    
    def run_all(self):
        """Run all tests"""
        print("=" * 60)
        print("Running cleanup.py tests")
        print("=" * 60)
        
        try:
            self.setup()
            
            self.test_junk_file_detection()
            self.test_non_junk_file_detection()
            self.test_read_file_content()
            self.test_get_git_status_empty()
            self.test_get_git_status_with_changes()
            self.test_get_untracked_files()
            self.test_get_all_tracked_files()
            self.test_generate_cleanup_plan()
            self.test_find_file_references()
            self.test_log_cleanup()
            
        finally:
            self.teardown()
        
        print("\n" + "=" * 60)
        print(f"Results: {self.passed} passed, {self.failed} failed")
        print("=" * 60)
        
        return self.failed == 0


if __name__ == "__main__":
    tester = TestCleanup()
    success = tester.run_all()
    sys.exit(0 if success else 1)
