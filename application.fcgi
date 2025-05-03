#!/home2/thougka3/public_html/contingencygroup/optimiser/venv/bin/python3.6
from flup.server.fcgi import WSGIServer
from fx1_api import app

if __name__ == '__main__':
    WSGIServer(app).run()
