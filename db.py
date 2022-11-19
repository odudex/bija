import json
import time
from os.path import exists

from sqlalchemy import create_engine, Column, Integer, String, Time, ForeignKey, Boolean, text, distinct, func
from sqlalchemy.orm import declarative_base, sessionmaker, join, relationship, subqueryload, aliased

Base = declarative_base()
DB_ENGINE = create_engine("sqlite:///bija.sqlite", echo=False)
DB_SESSION = sessionmaker(autocommit=False, autoflush=False, bind=DB_ENGINE)

DEFAULT_RELAYS = [
    'wss://nostr.drss.io',
    'wss://nostr-pub.wellorder.net',
    'wss://nostr-relay.wlvs.space'
]


class BijaDB:

    def __init__(self, session):
        # self.db_engine = create_engine("sqlite:///2.sqlite", echo=True)
        # s = sessionmaker(bind=self.db_engine)
        self.session = session
        if not exists("bija.sqlite"):
            self.setup()

    def setup(self):
        Base.metadata.create_all(DB_ENGINE)
        relays = []
        for r in DEFAULT_RELAYS:
            relays.append(Relay(name=r))
        self.session.add_all(relays)
        self.session.commit()

    def reset(self):
        self.session.query(Profile).delete()
        self.session.query(PrivateMessage).delete()
        self.session.query(Note).delete()
        self.session.query(PK).delete()
        self.session.commit()

    def get_relays(self):
        return self.session.query(Relay)

    def get_preferred_relay(self):
        return self.session.query(Relay).first()

    def get_profile(self, public_key):
        return self.session.query(Profile).filter_by(public_key=public_key).first()

    def get_saved_pk(self):
        print("GET SAVED")
        pk = self.session.query(PK).first()
        return pk

    def save_pk(self, key, enc):
        self.session.add(PK(
            key=key,
            enc=enc
        ))
        self.session.commit()

    def add_profile(self,
                    public_key,
                    name=None,
                    nip05=None,
                    pic=None,
                    about=None,
                    updated_at=None):
        if updated_at is None:
            updated_at = int(time.time())
        self.session.add(Profile(
            public_key=public_key,
            name=name,
            nip05=nip05,
            pic=pic,
            about=about,
            updated_at=updated_at
        ))
        self.session.commit()

    def add_contact_list(self, public_key, keys: list):
        self.session.merge(Profile(
            public_key=public_key,
            contacts=json.dumps(keys)
        ))
        self.session.commit()

    def set_following(self, keys_list, following=True):
        for public_key in keys_list:
            print(public_key, following)
            self.session.merge(Profile(
                public_key=public_key,
                following=following
            ))
        self.session.commit()

    def get_following_pubkeys(self):
        keys = self.session.query(Profile).filter_by(following=1).all()
        out = []
        for k in keys:
            out.append(k.public_key)
        return out

    def get_following(self):
        profiles = self.session.query(
            Profile.public_key,
            Profile.name,
            Profile.pic).filter_by(following=1).all()
        out = []
        for p in profiles:
            out.append(dict(p))
        return out

    def upd_profile(self,
                    public_key,
                    name=None,
                    nip05=None,
                    pic=None,
                    about=None,
                    updated_at=None):
        print("UPDATING PROFILE: ", public_key)
        self.session.merge(Profile(
            public_key=public_key,
            name=name,
            nip05=nip05,
            pic=pic,
            about=about,
            updated_at=updated_at
        ))
        self.session.commit()

    def insert_note(self,
                    note_id,
                    public_key,
                    content,
                    response_to=None,
                    thread_root=None,
                    created_at=None,
                    members=None):
        self.session.merge(Note(
            id=note_id,
            public_key=public_key,
            content=content,
            response_to=response_to,
            thread_root=thread_root,
            created_at=created_at,
            members=members
        ))
        self.session.commit()

    def is_note(self, note_id):
        return self.session.query(Note.id).filter_by(id=note_id).first()

    def is_known_pubkey(self, pk):
        return self.session.query(Profile.public_key).filter_by(public_key=pk).first()

    def get_note(self, note_id):
        return self.session.query(Note.id,
                                  Note.public_key,
                                  Note.content,
                                  Note.response_to,
                                  Note.thread_root,
                                  Note.created_at,
                                  Note.members,
                                  Profile.name,
                                  Profile.pic,
                                  Profile.nip05).filter_by(id=note_id).join(Note.profile).first()

    def get_note_thread(self, note_id):
        return self.session.query(Note.id,
                                  Note.public_key,
                                  Note.content,
                                  Note.response_to,
                                  Note.thread_root,
                                  Note.created_at,
                                  Note.members,
                                  Profile.name,
                                  Profile.pic,
                                  Profile.nip05)\
            .filter(text("note.id='{}' or note.response_to='{}' or note.thread_root='{}'".format(note_id, note_id, note_id)))\
            .join(Note.profile).order_by(Note.created_at.asc()).all()

    def insert_private_message(self,
                               msg_id,
                               public_key,
                               content,
                               is_sender,
                               created_at):
        self.session.merge(PrivateMessage(
            id=msg_id,
            public_key=public_key,
            content=content,
            is_sender=is_sender,
            created_at=created_at,
        ))
        self.session.commit()

    def get_feed(self, before, public_key):
        return self.session.query(
            Note.id,
            Note.public_key,
            Note.content,
            Note.response_to,
            Note.thread_root,
            Note.created_at,
            Note.members,
            Profile.name,
            Profile.pic,
            Profile.nip05).join(Note.profile).filter(text("note.created_at<{}".format(before)))\
            .filter(text("profile.following=1 OR profile.public_key='{}'".format(public_key)))\
            .order_by(Note.created_at.desc()).limit(50).all()

    def get_note_by_id_list(self, note_ids):
        return self.session.query(
            Note.id,
            Note.public_key,
            Note.content,
            Note.created_at,
            Note.members,
            Profile.name,
            Profile.pic,
            Profile.nip05).join(Note.profile).filter(Note.id.in_(note_ids)).all()

    def get_notes_by_pubkey(self, public_key, before, after):
        return self.session.query(
            Note.id,
            Note.public_key,
            Note.content,
            Note.response_to,
            Note.thread_root,
            Note.created_at,
            Note.members,
            Profile.name,
            Profile.pic,
            Profile.nip05).join(Note.profile).filter(text("note.created_at<{}".format(before))).filter_by(
            public_key=public_key).order_by(Note.created_at.desc()).limit(50).all()

    def get_profile_updates(self, public_key, last_update):
        return self.session.query(Profile).filter_by(public_key=public_key).filter(text("profile.updated_at>{}".format(last_update))).first()

    def get_message_list(self):
        return self.session.query(
            func.max(PrivateMessage.created_at).label("last_message"), Profile.public_key, Profile.name, Profile.pic, PrivateMessage.is_sender)\
            .join(Profile, Profile.public_key == PrivateMessage.public_key)\
            .order_by(PrivateMessage.created_at.desc()).group_by(PrivateMessage.public_key).all()

    def get_message_thread(self, public_key):
        return self.session.query(
            PrivateMessage.is_sender,
            PrivateMessage.content,
            PrivateMessage.created_at,
            PrivateMessage.public_key,
            Profile.name,
            Profile.pic)\
            .filter(text("profile.public_key = private_message.public_key AND private_message.public_key='{}'".format(public_key)))\
            .order_by(PrivateMessage.created_at.desc()).limit(100).all()


class Profile(Base):
    __tablename__ = "profile"
    public_key = Column(String(64), unique=True, primary_key=True)
    name = Column(String)
    nip05 = Column(String)
    pic = Column(String)
    about = Column(String)
    updated_at = Column(Integer)
    following = Column(Boolean)
    contacts = Column(String)

    notes = relationship("Note", back_populates="profile")

    def __repr__(self):
        return {
            self.public_key,
            self.name,
            self.nip05,
            self.pic,
            self.about,
            self.updated_at,
            self.following,
            self.contacts
        }


class Note(Base):
    __tablename__ = "note"
    id = Column(String(64), unique=True, primary_key=True)
    public_key = Column(String(64), ForeignKey("profile.public_key"))
    content = Column(String)
    response_to = Column(String(64))
    thread_root = Column(String(64))
    created_at = Column(Integer)
    members = Column(String)

    profile = relationship("Profile", back_populates="notes")

    def __repr__(self):
        return {
            self.id,
            self.public_key,
            self.content,
            self.response_to,
            self.thread_root,
            self.created_at,
            self.members
        }


class PrivateMessage(Base):
    __tablename__ = "private_message"
    id = Column(String(64), unique=True, primary_key=True)
    public_key = Column(String(64), ForeignKey("profile.public_key"))
    content = Column(String)
    is_sender = Column(Boolean)  # true = public_key is sender, false I'm sender
    created_at = Column(Integer)

    def __repr__(self):
        return {
            self.id,
            self.public_key,
            self.content,
            self.is_sender,
            self.created_at
        }


# Private keys
class PK(Base):
    __tablename__ = "PK"
    id = Column(Integer, primary_key=True)
    key = Column(String)
    enc = Column(Integer)  # boolean


class Relay(Base):
    __tablename__ = "relay"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True)
