"""Gedeelde pytest fixtures."""
import pytest
import sys
import os

# Voeg project root toe aan sys.path zodat imports werken
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
