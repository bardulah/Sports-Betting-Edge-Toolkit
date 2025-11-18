#!/usr/bin/env python3
"""
Run Dashboard
=============

Launch the Streamlit dashboard.
"""

import subprocess
import sys
import os

def main():
    dashboard_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'dashboard',
        'app.py'
    )

    subprocess.run([
        sys.executable, '-m', 'streamlit', 'run',
        dashboard_path,
        '--server.port', '8501',
        '--server.address', '0.0.0.0'
    ])


if __name__ == '__main__':
    main()
