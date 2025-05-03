import sys, os

# 1. Activate our venv
venv_root = os.path.join(os.path.dirname(__file__), 'venv')
activate = os.path.join(venv_root, 'bin/activate_this.py')
with open(activate) as f:
    exec(f.read(), {'__file__': activate})

# 2. Add project & venv site-packages to path
sys.path.insert(0, os.path.dirname(__file__))
site_packages = os.path.join(venv_root, 'lib/python3.8/site-packages')
sys.path.insert(0, site_packages)

# 3. Import your Flask WSGI app
from fx1_api import app as application
