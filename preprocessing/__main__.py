#!/usr/bin/env python3
"""
Main entry point for the preprocessing module.
Allows running as: python -m preprocessing
"""

import asyncio
from .cli import main

if __name__ == "__main__":
    exit(asyncio.run(main()))