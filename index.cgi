#!/home2/thougka3/public_html/contingencygroup/optimiser/venv/bin/python3.6

import cgitb
cgitb.enable(display=1)

import os, sys
# activate the venv
activate = os.path.join(os.path.dirname(__file__), 'venv/bin/activate_this.py')
with open(activate) as f:
    exec(f.read(), {'__file__': activate})

from wsgiref.handlers import CGIHandler
from fx1_api import app

CGIHandler().run(app)
