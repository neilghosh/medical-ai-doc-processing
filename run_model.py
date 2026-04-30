"""Deprecated shim. Moved to `scripts.run_model`. Safe to delete."""
import runpy

runpy.run_module("scripts.run_model", run_name="__main__")
