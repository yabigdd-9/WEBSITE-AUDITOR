"""Compatibility entrypoint for the authenticated local FastAPI portal."""
from auditor_toolkit.portal import create_app


def start_portal(port=8080, output_root='outputs/toolkit'):
    import uvicorn
    uvicorn.run(create_app(output_root), host='127.0.0.1', port=port)


if __name__ == '__main__':
    start_portal()
