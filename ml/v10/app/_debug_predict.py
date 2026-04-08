"""Debug script: launch app, wait for models, trigger predict, print any error."""
import os, sys, traceback, threading, time

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ".")

import surrogate_app as sa

# Patch error handler to print full traceback
_orig_err = sa.SurrogateApp._on_predict_error
def _patched_err(self, error):
    print("\n=== PREDICT ERROR ===", flush=True)
    print(repr(error), flush=True)
    traceback.print_exception(type(error), error, error.__traceback__)
    sys.stdout.flush()
    _orig_err(self, error)
sa.SurrogateApp._on_predict_error = _patched_err

# Also patch _gather_raw to see if it raises
_orig_gather = sa.SurrogateApp._gather_raw
def _patched_gather(self):
    try:
        result = _orig_gather(self)
        print(f"\n=== GATHER OK: {len(result)} keys ===", flush=True)
        return result
    except Exception as e:
        print(f"\n=== GATHER ERROR: {e} ===", flush=True)
        traceback.print_exc()
        raise
sa.SurrogateApp._gather_raw = _patched_gather

app = sa.SurrogateApp()

def try_predict():
    time.sleep(7)  # Wait for models to load
    print("\n=== TRIGGERING PREDICT ===", flush=True)
    app.after(0, app._on_predict)
    time.sleep(4)
    print("\n=== DONE, destroying ===", flush=True)
    app.after(0, app.destroy)

t = threading.Thread(target=try_predict, daemon=True)
t.start()
app.mainloop()
