#!/usr/bin/env python3
"""Test script to verify autonomous runner fixes"""

import json
import os
import sys

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

os.chdir(os.path.join(os.path.dirname(__file__), 'backend'))

# Test 1: Check that _load_assigned_projects filters paused projects
print("=== Test 1: Paused project filter ===")
try:
    from app.services.autonomous_runner import _load_assigned_projects
    
    agent_id = "83db009b-1db1-4256-b614-7f8513e7324a"
    projects = _load_assigned_projects(agent_id)
    
    print(f"✅ Function executes successfully")
    print(f"Total projects loaded: {len(projects)}")
    
    for p in projects:
        print(f"  - {p['name']:50s} status={p['status']:10s} pending={len(p['pending_tasks'])}")
    
    paused_count = sum(1 for p in projects if p['status'] == 'paused')
    if paused_count == 0:
        print("✅ PASS: No paused projects loaded")
    else:
        print(f"❌ FAIL: {paused_count} paused project(s) loaded")
        sys.exit(1)
        
except Exception as e:
    print(f"❌ FAIL: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n=== Test 2: Check syntax of autonomous_runner.py ===")
try:
    import py_compile
    py_compile.compile('app/services/autonomous_runner.py', doraise=True)
    print("✅ PASS: Syntax is valid")
except Exception as e:
    print(f"❌ FAIL: {e}")
    sys.exit(1)

print("\n✅ All tests passed!")
