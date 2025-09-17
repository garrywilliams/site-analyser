#!/usr/bin/env python3
"""
Main entry point for the preprocessing module.
Allows running as: python -m preprocessing
"""

from .cli import main

if __name__ == "__main__":
    exit(main())