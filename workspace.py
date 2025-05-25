

class WorkspaceManager:
    _instance = None
    path = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def set_workspace(cls, path):
        cls.get_instance().path = path

    @classmethod
    def get_workspace(cls):
        return cls.get_instance().path