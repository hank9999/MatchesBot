import dataclasses


@dataclasses.dataclass
class Match:
    _id: str
    name: str
    role1: str
    role2: str
    match_time: str
    map_name: str
    score: str
    channel: str = ''

    def todict(self):
        return dataclasses.asdict(self)

    @property
    def id(self):
        return self._id
