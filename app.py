import os
import sqlite3
import socket
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, Response, abort, g, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:  # pragma: no cover - optional for local SQLite-only runs
    psycopg = None
    dict_row = None

app = Flask(__name__)
app.secret_key = os.environ.get("ANIDEX_SECRET_KEY", "anidex-dev-secret")

BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = BASE_DIR / "anidex.db"
DATABASE_URL = os.environ.get("DATABASE_URL")
USE_POSTGRES = bool(DATABASE_URL)


def _normalize_database_url(url):
    if not url:
        return None
    if url.startswith("postgres://"):
        return "postgresql://" + url.removeprefix("postgres://")
    return url


class DatabaseProxy:
    def __init__(self, connection, backend):
        self.connection = connection
        self.backend = backend

    def _rewrite(self, sql):
        if self.backend != "postgres":
            return sql
        return sql.replace("?", "%s")

    def execute(self, sql, params=()):
        return self.connection.execute(self._rewrite(sql), params)

    def executemany(self, sql, params_seq):
        return self.connection.executemany(self._rewrite(sql), params_seq)

    def commit(self):
        return self.connection.commit()

    def close(self):
        return self.connection.close()


def connect_db():
    if USE_POSTGRES:
        if psycopg is None:
            raise RuntimeError("psycopg is required when DATABASE_URL is set.")
        connection = psycopg.connect(_normalize_database_url(DATABASE_URL), row_factory=dict_row)
        return DatabaseProxy(connection, "postgres")
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return DatabaseProxy(connection, "sqlite")


def is_postgres_db(db):
    return getattr(db, "backend", "sqlite") == "postgres"


def is_unique_constraint_error(error):
    if isinstance(error, sqlite3.IntegrityError):
        return True
    return getattr(error, "sqlstate", None) == "23505"


def seed_animal_rows():
    return [
        (
            animal["id"],
            animal["sort_order"],
            animal["name"],
            animal["scientific_name"],
            animal["category"],
            animal["region_id"],
            animal["habitat"],
            animal["diet"],
            animal["status"],
            animal["rarity"],
            animal["fact"],
            animal["description"],
            animal["emoji"],
        )
        for animal in (SEED_ANIMALS + EXTRA_SEED_ANIMALS + EXTRA_ZOO_ANIMALS)
    ]


def upsert_seed_animals(db):
    if is_postgres_db(db):
        sql = """
        INSERT INTO animals (
            id, sort_order, name, scientific_name, category, region_id, habitat, diet,
            status, rarity, fact, description, emoji
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
        ON CONFLICT (id) DO UPDATE SET
            sort_order = EXCLUDED.sort_order,
            name = EXCLUDED.name,
            scientific_name = EXCLUDED.scientific_name,
            category = EXCLUDED.category,
            region_id = EXCLUDED.region_id,
            habitat = EXCLUDED.habitat,
            diet = EXCLUDED.diet,
            status = EXCLUDED.status,
            rarity = EXCLUDED.rarity,
            fact = EXCLUDED.fact,
            description = EXCLUDED.description,
            emoji = EXCLUDED.emoji
        """
    else:
        sql = """
        INSERT OR REPLACE INTO animals (
            id, sort_order, name, scientific_name, category, region_id, habitat, diet,
            status, rarity, fact, description, emoji
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
        """
    db.executemany(sql, seed_animal_rows())


def upsert_progress(db, user_id, animal_id, discovered_at):
    if is_postgres_db(db):
        db.execute(
            """
            INSERT INTO progress (user_id, animal_id, discovered_at)
            VALUES (?, ?, ?)
            ON CONFLICT (user_id, animal_id)
            DO UPDATE SET discovered_at = EXCLUDED.discovered_at
            """,
            (user_id, animal_id, discovered_at),
        )
    else:
        db.execute(
            """
            INSERT OR REPLACE INTO progress (user_id, animal_id, discovered_at)
            VALUES (?, ?, ?)
            """,
            (user_id, animal_id, discovered_at),
        )


REGIONS = [
    {"id": "region-1", "name": "Region 1", "label": "Region 1", "theme": "Starter Dex", "badge": "Explorer"},
]

DEFAULT_PROFILE = {
    "username": "Guest",
    "email": "",
    "is_authenticated": False,
}


SEED_ANIMALS = [
    {"id": "dog", "sort_order": 1, "name": "Dog", "scientific_name": "Canis lupus familiaris", "category": "Mammal", "region_id": "region-1", "habitat": "Homes and streets", "diet": "Omnivore", "status": "Domesticated", "rarity": "Common", "fact": "Dogs were among the first animals domesticated by humans.", "description": "A friendly everyday companion people see in homes, streets, and parks.", "emoji": "🐕"},
    {"id": "cat", "sort_order": 2, "name": "Cat", "scientific_name": "Felis catus", "category": "Mammal", "region_id": "region-1", "habitat": "Homes, rooftops, and lanes", "diet": "Carnivore", "status": "Domesticated", "rarity": "Common", "fact": "Cats can rotate their ears to track sounds from different directions.", "description": "A curious small hunter often found napping, climbing, and watching everything.", "emoji": "🐈"},
    {"id": "squirrel", "sort_order": 3, "name": "Squirrel", "scientific_name": "Funambulus palmarum", "category": "Mammal", "region_id": "region-1", "habitat": "Trees, parks, and gardens", "diet": "Omnivore", "status": "Least Concern", "rarity": "Common", "fact": "Squirrels are quick climbers and love seeds and fruit.", "description": "A striped little acrobat often seen racing along walls and branches.", "emoji": "🐿️"},
    {"id": "lizard", "sort_order": 4, "name": "Lizard", "scientific_name": "Calotes versicolor", "category": "Reptile", "region_id": "region-1", "habitat": "Walls, gardens, and yards", "diet": "Carnivore", "status": "Least Concern", "rarity": "Common", "fact": "Many common lizards help by eating insects around homes.", "description": "A small quick reptile often spotted basking on walls or darting through gardens.", "emoji": "🦎"},
    {"id": "sparrow", "sort_order": 5, "name": "Sparrow", "scientific_name": "Passer domesticus", "category": "Bird", "region_id": "region-1", "habitat": "Balconies, roofs, and markets", "diet": "Omnivore", "status": "Least Concern", "rarity": "Common", "fact": "Sparrows often build nests close to human homes.", "description": "A tiny chirping bird that fits perfectly into daily life scenes.", "emoji": "🐦‍⬛"},
    {"id": "myna", "sort_order": 6, "name": "Myna", "scientific_name": "Acridotheres tristis", "category": "Bird", "region_id": "region-1", "habitat": "Parks, roofs, and roadsides", "diet": "Omnivore", "status": "Least Concern", "rarity": "Common", "fact": "Mynas are bold walkers and often search for food on the ground.", "description": "A confident everyday bird seen walking, calling, and hopping around people.", "emoji": "🐦‍⬛"},
    {"id": "pigeon", "sort_order": 7, "name": "Pigeon", "scientific_name": "Columba livia", "category": "Bird", "region_id": "region-1", "habitat": "Buildings and public squares", "diet": "Omnivore", "status": "Least Concern", "rarity": "Common", "fact": "Pigeons can recognize landmarks and find their way home over long distances.", "description": "A very common city bird seen near buildings, wires, and stations.", "emoji": "🕊️"},
    {"id": "crow", "sort_order": 8, "name": "Crow", "scientific_name": "Corvus splendens", "category": "Bird", "region_id": "region-1", "habitat": "Roadsides and neighborhoods", "diet": "Omnivore", "status": "Least Concern", "rarity": "Common", "fact": "Crows are highly intelligent and remember faces.", "description": "A smart black bird that thrives wherever people live.", "emoji": "🐦‍⬛"},
    {"id": "kite", "sort_order": 9, "name": "Kite", "scientific_name": "Milvus migrans", "category": "Bird", "region_id": "region-1", "habitat": "Open skies and city edges", "diet": "Carnivore", "status": "Least Concern", "rarity": "Uncommon", "fact": "Kites are often seen circling high above cities and fields.", "description": "A soaring bird of prey that many people notice gliding overhead.", "emoji": "🪶"},
    {"id": "bat", "sort_order": 10, "name": "Bat", "scientific_name": "Pteropus giganteus", "category": "Mammal", "region_id": "region-1", "habitat": "Trees, old buildings, and evening skies", "diet": "Omnivore", "status": "Least Concern", "rarity": "Uncommon", "fact": "Bats are the only mammals capable of true flight.", "description": "A night-flying mammal that becomes visible around sunset.", "emoji": "🦇"},
    {"id": "cow", "sort_order": 11, "name": "Cow", "scientific_name": "Bos taurus indicus", "category": "Mammal", "region_id": "region-1", "habitat": "Homes, sheds, and roadsides", "diet": "Herbivore", "status": "Domesticated", "rarity": "Common", "fact": "Cows spend many hours a day chewing cud.", "description": "A calm grazing animal commonly seen around neighborhoods and villages.", "emoji": "🐄"},
    {"id": "goat", "sort_order": 12, "name": "Goat", "scientific_name": "Capra hircus", "category": "Mammal", "region_id": "region-1", "habitat": "Backyards and village lanes", "diet": "Herbivore", "status": "Domesticated", "rarity": "Common", "fact": "Goats are excellent climbers and love exploring elevated places.", "description": "A playful farm animal often seen wandering and nibbling on leaves.", "emoji": "🐐"},
    {"id": "buffalo", "sort_order": 13, "name": "Buffalo", "scientific_name": "Bubalus bubalis", "category": "Mammal", "region_id": "region-1", "habitat": "Fields and village ponds", "diet": "Herbivore", "status": "Domesticated", "rarity": "Common", "fact": "Buffalo often cool themselves by resting in water or mud.", "description": "A strong farm animal often seen near wet fields and rural roads.", "emoji": "🐃"},
    {"id": "monkey", "sort_order": 14, "name": "Monkey", "scientific_name": "Macaca mulatta", "category": "Mammal", "region_id": "region-1", "habitat": "Temple grounds and forest edges", "diet": "Omnivore", "status": "Least Concern", "rarity": "Uncommon", "fact": "Monkeys are adaptable and often live near human settlements.", "description": "A clever animal that many people do see, but one that needs caution.", "emoji": "🐒"},
    {"id": "mongoose", "sort_order": 15, "name": "Mongoose", "scientific_name": "Herpestes edwardsii", "category": "Mammal", "region_id": "region-1", "habitat": "Fields and village edges", "diet": "Carnivore", "status": "Least Concern", "rarity": "Uncommon", "fact": "Mongooses are famous for their speed when facing snakes.", "description": "A sharp, alert hunter that feels like a step up from everyday backyard animals.", "emoji": "🦦"},
    {"id": "rat", "sort_order": 16, "name": "Rat", "scientific_name": "Rattus rattus", "category": "Mammal", "region_id": "region-1", "habitat": "Homes, drains, and storage spaces", "diet": "Omnivore", "status": "Least Concern", "rarity": "Common", "fact": "Rats are excellent climbers and can live almost anywhere people do.", "description": "A quick adaptable animal commonly found near buildings and food sources.", "emoji": "🐀"},
    {"id": "frog", "sort_order": 17, "name": "Frog", "scientific_name": "Hoplobatrachus tigerinus", "category": "Amphibian", "region_id": "region-1", "habitat": "Ponds and wet grassy patches", "diet": "Carnivore", "status": "Least Concern", "rarity": "Common", "fact": "Some frogs are heard more often than they are seen.", "description": "A jumpy wetland animal people often hear at night before they see it.", "emoji": "🐸"},
    {"id": "toad", "sort_order": 18, "name": "Toad", "scientific_name": "Duttaphrynus melanostictus", "category": "Amphibian", "region_id": "region-1", "habitat": "Gardens, damp corners, and roadsides", "diet": "Carnivore", "status": "Least Concern", "rarity": "Common", "fact": "Toads usually have drier, bumpier skin than frogs.", "description": "A sturdy small amphibian often seen after rain or near damp ground.", "emoji": "🐸"},
    {"id": "donkey", "sort_order": 19, "name": "Donkey", "scientific_name": "Equus africanus asinus", "category": "Mammal", "region_id": "region-1", "habitat": "Roadsides, villages, and work yards", "diet": "Herbivore", "status": "Domesticated", "rarity": "Uncommon", "fact": "Donkeys are strong, sure-footed, and known for loud brays.", "description": "A hardworking animal that some people spot in towns and rural areas.", "emoji": "🫏"},
    {"id": "pig", "sort_order": 20, "name": "Pig", "scientific_name": "Sus scrofa domesticus", "category": "Mammal", "region_id": "region-1", "habitat": "Village edges and open lots", "diet": "Omnivore", "status": "Domesticated", "rarity": "Common", "fact": "Pigs are intelligent animals with a strong sense of smell.", "description": "A stocky everyday animal often seen around open ground and settlements.", "emoji": "🐖"},
    {"id": "heron", "sort_order": 21, "name": "Heron", "scientific_name": "Ardea cinerea", "category": "Bird", "region_id": "region-1", "habitat": "Ponds, lakes, and marsh edges", "diet": "Carnivore", "status": "Least Concern", "rarity": "Uncommon", "fact": "Herons can stand almost perfectly still while waiting for prey.", "description": "A tall water bird that feels special but still realistic to spot near ponds.", "emoji": "🪶"},
    {"id": "egret", "sort_order": 22, "name": "Egret", "scientific_name": "Bubulcus ibis", "category": "Bird", "region_id": "region-1", "habitat": "Fields, ponds, and wetlands", "diet": "Carnivore", "status": "Least Concern", "rarity": "Uncommon", "fact": "Egrets are often seen following cattle to catch disturbed insects.", "description": "A clean white bird that stands out beautifully in wet fields and shallow water.", "emoji": "🪶"},
    {"id": "kingfisher", "sort_order": 23, "name": "Kingfisher", "scientific_name": "Alcedo atthis", "category": "Bird", "region_id": "region-1", "habitat": "Ponds, canals, and streams", "diet": "Carnivore", "status": "Least Concern", "rarity": "Uncommon", "fact": "Kingfishers dive quickly into water to catch fish.", "description": "A bright, fast bird that makes pond spotting feel more exciting.", "emoji": "🐦‍⬛"},
    {"id": "duck", "sort_order": 24, "name": "Duck", "scientific_name": "Anas platyrhynchos domesticus", "category": "Bird", "region_id": "region-1", "habitat": "Ponds and water edges", "diet": "Omnivore", "status": "Domesticated", "rarity": "Common", "fact": "A duck's feathers help keep water from soaking through to the skin.", "description": "A familiar pond animal often spotted swimming in groups.", "emoji": "🦆"},
    {"id": "parrot", "sort_order": 25, "name": "Parrot", "scientific_name": "Psittacula krameri", "category": "Bird", "region_id": "region-1", "habitat": "Trees, parks, and gardens", "diet": "Herbivore", "status": "Least Concern", "rarity": "Uncommon", "fact": "Parrots are often heard before they are seen because of their loud calls.", "description": "A bright green bird that adds color and noise to city trees.", "emoji": "🦜"},
]

EXTRA_SEED_ANIMALS = [
    {"id": "hare", "sort_order": 26, "name": "Hare", "scientific_name": "Lepus nigricollis", "category": "Mammal", "region_id": "region-1", "habitat": "Fields and grasslands", "diet": "Herbivore", "status": "Least Concern", "rarity": "Uncommon", "fact": "Hares are fast runners with strong back legs.", "description": "A quick wild rabbit-like animal often seen darting through open fields.", "emoji": "🐇"},
    {"id": "rabbit", "sort_order": 27, "name": "Rabbit", "scientific_name": "Oryctolagus cuniculus", "category": "Mammal", "region_id": "region-1", "habitat": "Farmland and grassy patches", "diet": "Herbivore", "status": "Domesticated", "rarity": "Common", "fact": "Rabbits use their long ears to hear danger.", "description": "A small soft animal people often keep as a pet.", "emoji": "🐰"},
    {"id": "horse", "sort_order": 28, "name": "Horse", "scientific_name": "Equus ferus caballus", "category": "Mammal", "region_id": "region-1", "habitat": "Stables, roads, and open fields", "diet": "Herbivore", "status": "Domesticated", "rarity": "Common", "fact": "Horses have been used for transport for thousands of years.", "description": "A strong fast animal that people still see in towns and villages.", "emoji": "🐎"},
    {"id": "ox", "sort_order": 29, "name": "Ox", "scientific_name": "Bos taurus", "category": "Mammal", "region_id": "region-1", "habitat": "Farms and fields", "diet": "Herbivore", "status": "Domesticated", "rarity": "Common", "fact": "Oxen are often trained to pull loads and farm equipment.", "description": "A sturdy work animal seen in rural places and on farm roads.", "emoji": "🐄"},
    {"id": "camel", "sort_order": 30, "name": "Camel", "scientific_name": "Camelus dromedarius", "category": "Mammal", "region_id": "region-1", "habitat": "Desert edges and dry roads", "diet": "Herbivore", "status": "Domesticated", "rarity": "Uncommon", "fact": "Camels can go a long time without drinking water.", "description": "A tall desert animal many people spot in western India.", "emoji": "🐪"},
    {"id": "sheep", "sort_order": 31, "name": "Sheep", "scientific_name": "Ovis aries", "category": "Mammal", "region_id": "region-1", "habitat": "Farms and hill grasslands", "diet": "Herbivore", "status": "Domesticated", "rarity": "Common", "fact": "Sheep often stay close to a flock for safety.", "description": "A fluffy farm animal seen in groups on grazing land.", "emoji": "🐑"},
    {"id": "hen", "sort_order": 32, "name": "Hen", "scientific_name": "Gallus gallus domesticus", "category": "Bird", "region_id": "region-1", "habitat": "Backyards and farms", "diet": "Omnivore", "status": "Domesticated", "rarity": "Common", "fact": "Hens scratch the ground to find food.", "description": "A common farm bird that people often see walking around yards.", "emoji": "🐔"},
    {"id": "rooster", "sort_order": 33, "name": "Rooster", "scientific_name": "Gallus gallus domesticus", "category": "Bird", "region_id": "region-1", "habitat": "Farms and village yards", "diet": "Omnivore", "status": "Domesticated", "rarity": "Common", "fact": "Roosters are known for their loud crowing.", "description": "A bright farm bird that announces the morning.", "emoji": "🐓"},
    {"id": "chick", "sort_order": 34, "name": "Chick", "scientific_name": "Gallus gallus domesticus", "category": "Bird", "region_id": "region-1", "habitat": "Farms and coops", "diet": "Omnivore", "status": "Domesticated", "rarity": "Common", "fact": "Chicks stay close to warmth and protection.", "description": "A tiny baby bird often seen running in groups.", "emoji": "🐥"},
    {"id": "peacock", "sort_order": 35, "name": "Peacock", "scientific_name": "Pavo cristatus", "category": "Bird", "region_id": "region-1", "habitat": "Fields, gardens, and forests", "diet": "Omnivore", "status": "Least Concern", "rarity": "Uncommon", "fact": "Peacocks are famous for their long colorful tail feathers.", "description": "A striking bird many people see in parks and countryside areas.", "emoji": "🦚"},
    {"id": "owl", "sort_order": 36, "name": "Owl", "scientific_name": "Strigiformes", "category": "Bird", "region_id": "region-1", "habitat": "Trees and quiet rooftops", "diet": "Carnivore", "status": "Least Concern", "rarity": "Uncommon", "fact": "Owls can turn their heads a long way.", "description": "A night bird with silent wings and a sharp stare.", "emoji": "🦉"},
    {"id": "eagle", "sort_order": 37, "name": "Eagle", "scientific_name": "Aquila", "category": "Bird", "region_id": "region-1", "habitat": "Cliffs, hills, and open skies", "diet": "Carnivore", "status": "Least Concern", "rarity": "Rare", "fact": "Eagles have very powerful eyesight.", "description": "A large bird of prey often seen circling far above the ground.", "emoji": "🦅"},
    {"id": "hawk", "sort_order": 38, "name": "Hawk", "scientific_name": "Accipiter", "category": "Bird", "region_id": "region-1", "habitat": "Open country and tree lines", "diet": "Carnivore", "status": "Least Concern", "rarity": "Uncommon", "fact": "Hawks are fast hunters with strong talons.", "description": "A sharp-eyed bird that glides and dives with precision.", "emoji": "🦅"},
    {"id": "snake", "sort_order": 39, "name": "Snake", "scientific_name": "Serpentes", "category": "Reptile", "region_id": "region-1", "habitat": "Fields, rocks, and gardens", "diet": "Carnivore", "status": "Least Concern", "rarity": "Uncommon", "fact": "Snakes do not have legs and move by sliding their scales.", "description": "A slithering reptile that people may see after rain or in dry grass.", "emoji": "🐍"},
    {"id": "cobra", "sort_order": 40, "name": "Cobra", "scientific_name": "Naja naja", "category": "Reptile", "region_id": "region-1", "habitat": "Fields and forest edges", "diet": "Carnivore", "status": "Least Concern", "rarity": "Rare", "fact": "Cobras can raise part of their body when threatened.", "description": "A famous snake with a hood that feels serious and dangerous.", "emoji": "🐍"},
    {"id": "python", "sort_order": 41, "name": "Python", "scientific_name": "Python molurus", "category": "Reptile", "region_id": "region-1", "habitat": "Wetlands and grasslands", "diet": "Carnivore", "status": "Least Concern", "rarity": "Rare", "fact": "Pythons squeeze their prey instead of using venom.", "description": "A large powerful snake seen much less often than small garden reptiles.", "emoji": "🐍"},
    {"id": "turtle", "sort_order": 42, "name": "Turtle", "scientific_name": "Testudines", "category": "Reptile", "region_id": "region-1", "habitat": "Ponds and slow rivers", "diet": "Omnivore", "status": "Least Concern", "rarity": "Uncommon", "fact": "Turtles can live in water and on land depending on the species.", "description": "A slow shelled animal often seen near calm water.", "emoji": "🐢"},
    {"id": "tortoise", "sort_order": 43, "name": "Tortoise", "scientific_name": "Testudinidae", "category": "Reptile", "region_id": "region-1", "habitat": "Dry ground and gardens", "diet": "Herbivore", "status": "Least Concern", "rarity": "Uncommon", "fact": "Tortoises spend almost all their lives on land.", "description": "A slow land reptile with a strong shell.", "emoji": "🐢"},
    {"id": "gecko", "sort_order": 44, "name": "Gecko", "scientific_name": "Gekkonidae", "category": "Reptile", "region_id": "region-1", "habitat": "Walls and ceilings", "diet": "Carnivore", "status": "Least Concern", "rarity": "Common", "fact": "Geckos can stick to smooth surfaces with their feet.", "description": "A tiny wall-climbing reptile many people see at home.", "emoji": "🦎"},
    {"id": "carp", "sort_order": 45, "name": "Carp", "scientific_name": "Cyprinus carpio", "category": "Fish", "region_id": "region-1", "habitat": "Ponds and lakes", "diet": "Omnivore", "status": "Least Concern", "rarity": "Common", "fact": "Carp are hardy fish that live in still water.", "description": "A common freshwater fish found in ponds and tanks.", "emoji": "🐟"},
    {"id": "catfish", "sort_order": 46, "name": "Catfish", "scientific_name": "Siluriformes", "category": "Fish", "region_id": "region-1", "habitat": "Rivers and muddy water", "diet": "Omnivore", "status": "Least Concern", "rarity": "Uncommon", "fact": "Catfish often have whisker-like barbels near their mouth.", "description": "A bottom-dwelling fish that lives in rivers and ponds.", "emoji": "🐟"},
    {"id": "crab", "sort_order": 47, "name": "Crab", "scientific_name": "Brachyura", "category": "Crustacean", "region_id": "region-1", "habitat": "Shorelines and river edges", "diet": "Omnivore", "status": "Least Concern", "rarity": "Uncommon", "fact": "Crabs walk sideways because of how their legs are built.", "description": "A sideways-walking water edge animal people spot near coasts and streams.", "emoji": "🦀"},
    {"id": "snail", "sort_order": 48, "name": "Snail", "scientific_name": "Gastropoda", "category": "Mollusk", "region_id": "region-1", "habitat": "Gardens and damp soil", "diet": "Herbivore", "status": "Least Concern", "rarity": "Common", "fact": "Snails move using a single muscular foot.", "description": "A slow shell animal that appears after rain.", "emoji": "🐌"},
    {"id": "butterfly", "sort_order": 49, "name": "Butterfly", "scientific_name": "Lepidoptera", "category": "Insect", "region_id": "region-1", "habitat": "Gardens and flowering plants", "diet": "Herbivore", "status": "Least Concern", "rarity": "Common", "fact": "Butterflies taste with their feet.", "description": "A colorful fluttering insect seen around flowers.", "emoji": "🦋"},
    {"id": "bee", "sort_order": 50, "name": "Bee", "scientific_name": "Apidae", "category": "Insect", "region_id": "region-1", "habitat": "Gardens, trees, and fields", "diet": "Herbivore", "status": "Least Concern", "rarity": "Common", "fact": "Bees help pollinate many of the plants people eat.", "description": "A tiny buzzing pollinator that is easy to find near flowers.", "emoji": "🐝"},
    {"id": "ant", "sort_order": 51, "name": "Ant", "scientific_name": "Formicidae", "category": "Insect", "region_id": "region-1", "habitat": "Soil, kitchens, and sidewalks", "diet": "Omnivore", "status": "Least Concern", "rarity": "Common", "fact": "Ants live in organized colonies with many workers.", "description": "A tiny social insect people see almost everywhere.", "emoji": "🐜"},
    {"id": "spider", "sort_order": 52, "name": "Spider", "scientific_name": "Araneae", "category": "Arachnid", "region_id": "region-1", "habitat": "Corners, plants, and walls", "diet": "Carnivore", "status": "Least Concern", "rarity": "Common", "fact": "Spiders have eight legs and spin webs for hunting.", "description": "A small eight-legged hunter found in many homes and gardens.", "emoji": "🕷️"},
    {"id": "dragonfly", "sort_order": 53, "name": "Dragonfly", "scientific_name": "Odonata", "category": "Insect", "region_id": "region-1", "habitat": "Ponds and wet fields", "diet": "Carnivore", "status": "Least Concern", "rarity": "Uncommon", "fact": "Dragonflies are skilled fliers that hunt other insects in the air.", "description": "A fast-flying insect often seen near water.", "emoji": "🪰"},
    {"id": "grasshopper", "sort_order": 54, "name": "Grasshopper", "scientific_name": "Caelifera", "category": "Insect", "region_id": "region-1", "habitat": "Grass, fields, and roadsides", "diet": "Herbivore", "status": "Least Concern", "rarity": "Common", "fact": "Grasshoppers can jump many times their body length.", "description": "A jumping insect that blends in with fields and grass.", "emoji": "🦗"},
    {"id": "deer", "sort_order": 55, "name": "Deer", "scientific_name": "Cervidae", "category": "Mammal", "region_id": "region-1", "habitat": "Forests and fields", "diet": "Herbivore", "status": "Least Concern", "rarity": "Uncommon", "fact": "Many deer have antlers that grow and shed over time.", "description": "A graceful forest animal seen in some grassy areas and parks.", "emoji": "🦌"},
    {"id": "boar", "sort_order": 56, "name": "Boar", "scientific_name": "Sus scrofa", "category": "Mammal", "region_id": "region-1", "habitat": "Forest edges and fields", "diet": "Omnivore", "status": "Least Concern", "rarity": "Rare", "fact": "Boars are strong wild relatives of domestic pigs.", "description": "A tough wild pig-like animal that people do not see every day.", "emoji": "🐗"},
    {"id": "fox", "sort_order": 57, "name": "Fox", "scientific_name": "Vulpes", "category": "Mammal", "region_id": "region-1", "habitat": "Grasslands and scrub", "diet": "Carnivore", "status": "Least Concern", "rarity": "Rare", "fact": "Foxes are known for their sharp ears and quick movement.", "description": "A clever wild animal with a long tail and pointed face.", "emoji": "🦊"},
    {"id": "jackal", "sort_order": 58, "name": "Jackal", "scientific_name": "Canis aureus", "category": "Mammal", "region_id": "region-1", "habitat": "Open land and scrub", "diet": "Omnivore", "status": "Least Concern", "rarity": "Rare", "fact": "Jackals often travel in pairs or small groups.", "description": "A wild canine that is easier to hear than to spot.", "emoji": "🦊"},
    {"id": "mole", "sort_order": 59, "name": "Mole", "scientific_name": "Talpidae", "category": "Mammal", "region_id": "region-1", "habitat": "Soil and grasslands", "diet": "Insectivore", "status": "Least Concern", "rarity": "Uncommon", "fact": "Moles spend much of their life underground.", "description": "A small digging mammal that rarely comes into view.", "emoji": "🐁"},
    {"id": "seal", "sort_order": 60, "name": "Seal", "scientific_name": "Pinnipedia", "category": "Mammal", "region_id": "region-1", "habitat": "Coasts and rocky shores", "diet": "Carnivore", "status": "Least Concern", "rarity": "Rare", "fact": "Seals are strong swimmers and can rest on land too.", "description": "A coastal animal that makes the first dex feel broader.", "emoji": "🦭"},
]

EXTRA_ZOO_ANIMALS = [
    {"id": "lion", "sort_order": 61, "name": "Lion", "scientific_name": "Panthera leo", "category": "Zoo", "region_id": "region-1", "habitat": "Zoos and safari parks", "diet": "Carnivore", "status": "Zoo", "rarity": "Rare", "fact": "Lions sleep for many hours a day, often more than 15.", "description": "A powerful big cat that people usually see in zoos rather than in the wild.", "emoji": "🦁"},
    {"id": "tiger", "sort_order": 62, "name": "Tiger", "scientific_name": "Panthera tigris", "category": "Zoo", "region_id": "region-1", "habitat": "Zoos and safari parks", "diet": "Carnivore", "status": "Zoo", "rarity": "Rare", "fact": "Tiger stripes are unique like fingerprints.", "description": "A striped big cat that is one of the most requested zoo animals.", "emoji": "🐯"},
    {"id": "leopard", "sort_order": 63, "name": "Leopard", "scientific_name": "Panthera pardus", "category": "Zoo", "region_id": "region-1", "habitat": "Zoos and wildlife parks", "diet": "Carnivore", "status": "Zoo", "rarity": "Rare", "fact": "Leopards can carry prey up trees.", "description": "A spotted big cat often kept in large zoo enclosures.", "emoji": "🐆"},
    {"id": "cheetah", "sort_order": 64, "name": "Cheetah", "scientific_name": "Acinonyx jubatus", "category": "Zoo", "region_id": "region-1", "habitat": "Zoos and safari parks", "diet": "Carnivore", "status": "Zoo", "rarity": "Rare", "fact": "Cheetahs are the fastest land animals.", "description": "A sleek big cat with a long body and a racing look.", "emoji": "🐆"},
    {"id": "bear", "sort_order": 65, "name": "Bear", "scientific_name": "Ursidae", "category": "Zoo", "region_id": "region-1", "habitat": "Zoos and mountain exhibits", "diet": "Omnivore", "status": "Zoo", "rarity": "Rare", "fact": "Bears can run faster than many people expect.", "description": "A big heavy animal most people know from zoo visits.", "emoji": "🐻"},
    {"id": "panda", "sort_order": 66, "name": "Panda", "scientific_name": "Ailuropoda melanoleuca", "category": "Zoo", "region_id": "region-1", "habitat": "Zoos and special exhibits", "diet": "Herbivore", "status": "Zoo", "rarity": "Mythic", "fact": "Pandas spend most of their day eating bamboo.", "description": "A famous black and white zoo animal that feels like a highlight entry.", "emoji": "🐼"},
    {"id": "gorilla", "sort_order": 67, "name": "Gorilla", "scientific_name": "Gorilla", "category": "Zoo", "region_id": "region-1", "habitat": "Zoos and primate houses", "diet": "Herbivore", "status": "Zoo", "rarity": "Rare", "fact": "Gorillas share a large amount of DNA with humans.", "description": "A strong great ape that many people only see in zoos.", "emoji": "🦍"},
    {"id": "chimpanzee", "sort_order": 68, "name": "Chimpanzee", "scientific_name": "Pan troglodytes", "category": "Zoo", "region_id": "region-1", "habitat": "Zoos and primate houses", "diet": "Omnivore", "status": "Zoo", "rarity": "Rare", "fact": "Chimpanzees use tools in the wild.", "description": "A clever ape that people often find fascinating to watch.", "emoji": "🐒"},
    {"id": "orangutan", "sort_order": 69, "name": "Orangutan", "scientific_name": "Pongo", "category": "Zoo", "region_id": "region-1", "habitat": "Zoos and rainforest exhibits", "diet": "Omnivore", "status": "Zoo", "rarity": "Rare", "fact": "Orangutans are known for their long arms and calm movement.", "description": "A big orange ape that makes zoo collections feel more global.", "emoji": "🦧"},
    {"id": "lemur", "sort_order": 70, "name": "Lemur", "scientific_name": "Lemuroidea", "category": "Zoo", "region_id": "region-1", "habitat": "Zoos and tropical exhibits", "diet": "Omnivore", "status": "Zoo", "rarity": "Uncommon", "fact": "Many lemurs use scent to communicate.", "description": "A small ring-tailed primate people usually know from zoo visits.", "emoji": "🐒"},
    {"id": "meerkat", "sort_order": 71, "name": "Meerkat", "scientific_name": "Suricata suricatta", "category": "Zoo", "region_id": "region-1", "habitat": "Zoos and desert exhibits", "diet": "Omnivore", "status": "Zoo", "rarity": "Uncommon", "fact": "Meerkats take turns standing guard while others dig or eat.", "description": "A tiny upright animal that feels playful and easy to remember.", "emoji": "🐿️"},
    {"id": "zebra", "sort_order": 72, "name": "Zebra", "scientific_name": "Equus quagga", "category": "Zoo", "region_id": "region-1", "habitat": "Zoos and safari parks", "diet": "Herbivore", "status": "Zoo", "rarity": "Rare", "fact": "No two zebras have exactly the same stripe pattern.", "description": "A striped horse-like animal that stands out immediately in zoos.", "emoji": "🦓"},
    {"id": "giraffe", "sort_order": 73, "name": "Giraffe", "scientific_name": "Giraffa camelopardalis", "category": "Zoo", "region_id": "region-1", "habitat": "Zoos and safari parks", "diet": "Herbivore", "status": "Zoo", "rarity": "Rare", "fact": "A giraffe's tongue can be very long and dark in color.", "description": "A towering zoo animal with a long neck and spotted coat.", "emoji": "🦒"},
    {"id": "hippo", "sort_order": 74, "name": "Hippo", "scientific_name": "Hippopotamus amphibius", "category": "Zoo", "region_id": "region-1", "habitat": "Zoos and water exhibits", "diet": "Herbivore", "status": "Zoo", "rarity": "Rare", "fact": "Hippos spend much of the day in water to stay cool.", "description": "A huge semi-aquatic animal that feels bigger than life in a zoo.", "emoji": "🦛"},
    {"id": "rhino", "sort_order": 75, "name": "Rhino", "scientific_name": "Rhinocerotidae", "category": "Zoo", "region_id": "region-1", "habitat": "Zoos and safari parks", "diet": "Herbivore", "status": "Zoo", "rarity": "Rare", "fact": "Rhinoceroses have very thick skin that looks like armor.", "description": "A tank-like animal that is iconic in any zoo lineup.", "emoji": "🦏"},
    {"id": "kangaroo", "sort_order": 76, "name": "Kangaroo", "scientific_name": "Macropus", "category": "Zoo", "region_id": "region-1", "habitat": "Zoos and open exhibits", "diet": "Herbivore", "status": "Zoo", "rarity": "Rare", "fact": "Kangaroos use their tails for balance while hopping.", "description": "A hopping animal that many people only see in zoos.", "emoji": "🦘"},
    {"id": "penguin", "sort_order": 77, "name": "Penguin", "scientific_name": "Spheniscidae", "category": "Zoo", "region_id": "region-1", "habitat": "Zoos and cold exhibits", "diet": "Carnivore", "status": "Zoo", "rarity": "Rare", "fact": "Penguins are birds that cannot fly.", "description": "A black and white bird that always feels special to see.", "emoji": "🐧"},
    {"id": "flamingo", "sort_order": 78, "name": "Flamingo", "scientific_name": "Phoenicopterus", "category": "Zoo", "region_id": "region-1", "habitat": "Zoos and wetlands", "diet": "Omnivore", "status": "Zoo", "rarity": "Uncommon", "fact": "Flamingos are pink because of what they eat.", "description": "A tall pink bird that makes zoo ponds stand out.", "emoji": "🦩"},
    {"id": "ostrich", "sort_order": 79, "name": "Ostrich", "scientific_name": "Struthio camelus", "category": "Zoo", "region_id": "region-1", "habitat": "Zoos and open exhibits", "diet": "Omnivore", "status": "Zoo", "rarity": "Rare", "fact": "Ostriches lay the largest eggs of any living bird.", "description": "A giant flightless bird that is hard to forget once seen.", "emoji": "🦤"},
    {"id": "crocodile", "sort_order": 80, "name": "Crocodile", "scientific_name": "Crocodylidae", "category": "Zoo", "region_id": "region-1", "habitat": "Zoos and reptile houses", "diet": "Carnivore", "status": "Zoo", "rarity": "Rare", "fact": "Crocodiles can stay very still for long periods while waiting.", "description": "A powerful reptile that adds a serious edge to the zoo block.", "emoji": "🐊"},
]


def get_db():
    if "db" not in g:
        g.db = connect_db()
    return g.db


@app.teardown_appcontext
def close_db(_error):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = connect_db()
    if is_postgres_db(db):
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS animals (
                id TEXT PRIMARY KEY,
                sort_order INTEGER NOT NULL,
                name TEXT NOT NULL,
                scientific_name TEXT NOT NULL,
                category TEXT NOT NULL,
                region_id TEXT NOT NULL,
                habitat TEXT NOT NULL,
                diet TEXT NOT NULL,
                status TEXT NOT NULL,
                rarity TEXT NOT NULL,
                fact TEXT NOT NULL,
                description TEXT NOT NULL,
                emoji TEXT NOT NULL
            )
            """
        )
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id BIGSERIAL PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS progress (
                user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                animal_id TEXT NOT NULL,
                discovered_at TEXT NOT NULL,
                PRIMARY KEY (user_id, animal_id)
            )
            """
        )
    else:
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS animals (
                id TEXT PRIMARY KEY,
                sort_order INTEGER NOT NULL,
                name TEXT NOT NULL,
                scientific_name TEXT NOT NULL,
                category TEXT NOT NULL,
                region_id TEXT NOT NULL,
                habitat TEXT NOT NULL,
                diet TEXT NOT NULL,
                status TEXT NOT NULL,
                rarity TEXT NOT NULL,
                fact TEXT NOT NULL,
                description TEXT NOT NULL,
                emoji TEXT NOT NULL
            )
            """
        )
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS progress (
                user_id INTEGER NOT NULL,
                animal_id TEXT NOT NULL,
                discovered_at TEXT NOT NULL,
                PRIMARY KEY (user_id, animal_id),
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """
        )
    upsert_seed_animals(db)
    db.commit()
    db.close()


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def get_current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    row = get_db().execute(
        "SELECT id, username, email, created_at FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()
    return dict(row) if row else None


def get_user_progress(user_id):
    rows = get_db().execute(
        "SELECT animal_id FROM progress WHERE user_id = ? ORDER BY discovered_at",
        (user_id,),
    ).fetchall()
    return [row["animal_id"] for row in rows]


def get_profile_payload():
    user = get_current_user()
    if not user:
        return DEFAULT_PROFILE
    return {
        "username": user["username"],
        "email": user["email"],
        "is_authenticated": True,
        "created_at": user["created_at"],
        "progress": get_user_progress(user["id"]),
    }


@app.context_processor
def inject_globals():
    user = get_current_user()
    progress = get_user_progress(user["id"]) if user else []
    return {
        "current_user": user or DEFAULT_PROFILE,
        "is_authenticated": bool(user),
        "server_progress": progress,
    }


def fetch_animals():
    rows = get_db().execute("SELECT * FROM animals ORDER BY sort_order").fetchall()
    return [dict(row) for row in rows]


def fetch_animal(animal_id):
    row = get_db().execute("SELECT * FROM animals WHERE id = ?", (animal_id,)).fetchone()
    return dict(row) if row else None


def build_regions():
    animals = fetch_animals()
    by_region = {}
    for animal in animals:
        by_region.setdefault(animal["region_id"], []).append(animal)

    regions = []
    for region in REGIONS:
        region_copy = dict(region)
        region_copy["animals"] = by_region.get(region["id"], [])
        region_copy["count"] = len(region_copy["animals"])
        regions.append(region_copy)
    return regions, animals


@app.route("/")
def index():
    regions, animals = build_regions()
    return render_template("index.html", regions=regions, animals=animals, today_label=datetime.now().strftime("%b %d, %Y"))


@app.route("/animal/<animal_id>")
def animal_detail(animal_id):
    animal = fetch_animal(animal_id)
    if not animal:
        abort(404)
    region = next((item for item in REGIONS if item["id"] == animal["region_id"]), None)
    return render_template("animal.html", animal=animal, region=region)


@app.route("/api/animals")
def animals_api():
    return jsonify(fetch_animals())


@app.route("/scan")
def scan():
    return render_template("scan.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        row = get_db().execute(
            "SELECT id, username, email, password_hash FROM users WHERE email = ?",
            (email,),
        ).fetchone()
        if row and check_password_hash(row["password_hash"], password):
            session["user_id"] = row["id"]
            return redirect(request.args.get("next") or url_for("profile"))
        error = "Invalid email or password."
    return render_template("auth.html", mode="login", error=error)


@app.route("/signup", methods=["GET", "POST"])
def signup():
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if len(username) < 3:
            error = "Username needs at least 3 characters."
        elif "@" not in email:
            error = "Enter a valid email."
        elif len(password) < 6:
            error = "Password needs at least 6 characters."
        else:
            try:
                db = get_db()
                if is_postgres_db(db):
                    cursor = db.execute(
                        """
                        INSERT INTO users (username, email, password_hash, created_at)
                        VALUES (?, ?, ?, ?)
                        RETURNING id
                        """,
                        (username, email, generate_password_hash(password), now_iso()),
                    )
                    user_id = cursor.fetchone()["id"]
                else:
                    cursor = db.execute(
                        "INSERT INTO users (username, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
                        (username, email, generate_password_hash(password), now_iso()),
                    )
                    user_id = cursor.lastrowid
                get_db().commit()
                session["user_id"] = user_id
                return redirect(url_for("profile"))
            except Exception as exc:
                if is_unique_constraint_error(exc):
                    error = "That username or email is already in use."
                else:
                    raise
    return render_template("auth.html", mode="signup", error=error)


@app.route("/logout")
def logout():
    session.pop("user_id", None)
    return redirect(url_for("index"))


@app.route("/profile")
def profile():
    user = get_current_user()
    if not user:
        return redirect(url_for("login", next=url_for("profile")))
    animals = fetch_animals()
    discovered_ids = set(get_user_progress(user["id"]))
    discovered_animals = [animal for animal in animals if animal["id"] in discovered_ids]
    return render_template("profile.html", user=user, discovered_animals=discovered_animals, total=len(animals))


@app.route("/api/me")
def api_me():
    return jsonify(get_profile_payload())


@app.route("/api/progress", methods=["GET", "POST", "DELETE"])
def api_progress():
    user = get_current_user()
    if not user:
        return jsonify({"error": "Login required"}), 401

    if request.method == "GET":
        return jsonify({"discovered": get_user_progress(user["id"])})

    data = request.get_json(silent=True) or {}
    action = data.get("action", "toggle")
    animal_id = data.get("animal_id")

    if action == "clear":
        get_db().execute("DELETE FROM progress WHERE user_id = ?", (user["id"],))
        get_db().commit()
        return jsonify({"ok": True, "discovered": []})

    if not animal_id:
        return jsonify({"error": "Missing animal_id"}), 400

    discovered = set(get_user_progress(user["id"]))
    if action == "remove":
        discovered.discard(animal_id)
    elif action == "add":
        discovered.add(animal_id)
    else:
        if animal_id in discovered:
            discovered.discard(animal_id)
        else:
            discovered.add(animal_id)

    db = get_db()
    db.execute("DELETE FROM progress WHERE user_id = ? AND animal_id = ?", (user["id"], animal_id))
    if animal_id in discovered:
        upsert_progress(db, user["id"], animal_id, now_iso())
    db.commit()
    return jsonify({"ok": True, "discovered": list(discovered)})


@app.route("/api/recognize", methods=["POST"])
def recognize():
    image = request.files.get("image")
    if not image:
        return jsonify({"error": "No image uploaded"}), 400

    # Phase 2 hook: swap this with a real vision model or API.
    # For now we return the most likely starter entry so the camera flow works end-to-end.
    return jsonify(
        {
            "detected": "Dog",
            "confidence": 0.32,
            "alternatives": [
                {"name": "Cat", "confidence": 0.18},
                {"name": "Crow", "confidence": 0.11},
                {"name": "Sparrow", "confidence": 0.09},
            ],
            "note": "Camera pipeline is wired. Connect a real vision model next for true recognition.",
        }
    )


@app.route("/manifest.webmanifest")
def manifest():
    return Response(
        """{
  "name": "Anidex",
  "short_name": "Anidex",
  "start_url": "/",
  "scope": "/",
  "display": "standalone",
  "background_color": "#b71b33",
  "theme_color": "#b71b33",
  "icons": [
    {
      "src": "/static/anidex-icon.svg",
      "sizes": "any",
      "type": "image/svg+xml"
    }
  ]
}""",
        mimetype="application/manifest+json",
    )


@app.route("/service-worker.js")
def service_worker():
    return Response(
        """
const CACHE_NAME = "anidex-cache-v1";
const ASSETS = ["/", "/scan", "/static/styles.css", "/static/app.js", "/static/anidex-icon.svg"];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(ASSETS)));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.map((key) => key !== CACHE_NAME && caches.delete(key))))
  );
});

self.addEventListener("fetch", (event) => {
  event.respondWith(
    caches.match(event.request).then((cached) => cached || fetch(event.request))
  );
});
""",
        mimetype="application/javascript",
    )


@app.route("/health")
def health():
    return {"ok": True}


def local_ip_address():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"


init_db()


if __name__ == "__main__":
    https_mode = os.environ.get("ANIDEX_HTTPS", "1") != "0"
    bind_mode = os.environ.get("ANIDEX_BIND_MODE", "all").lower()
    if bind_mode == "loopback":
        host = "127.0.0.1"
    elif bind_mode == "lan":
        host = local_ip_address()
    else:
        host = "0.0.0.0"
    scheme = "https" if https_mode else "http"
    print(f"Open {scheme}://{local_ip_address()}:5000 on your phone")
    app.run(
        debug=True,
        host=host,
        ssl_context="adhoc" if https_mode else None,
    )
