from .provider import Base, imported_target
import json
from . import other


class Child(Base):
    def run(self):
        imported_target()
        self.inherited()
        getattr(self, "dynamic")()


def local():
    imported_target()
    duplicate()
    json.dumps({"x": 1})
