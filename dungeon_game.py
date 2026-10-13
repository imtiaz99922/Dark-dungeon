"""
DARK FIGHT - A FANTASY DUNGEON
CSE 423 Lab Project - 3D Dungeon Crawler built with PyOpenGL / GLUT

A real-time 3D dungeon crawler: explore 4 connected rooms, fight three
monster types with a full AI state machine (idle/patrol/detect/chase/attack),
collect keys/potions/treasure, avoid pulsing floor traps, unlock a boss gate,
defeat a two-phase boss, and escape through the exit.

Run:
    pip install PyOpenGL PyOpenGL_accelerate
    python dungeon_game.py

Controls:
    W / S        Move forward / backward
    A / D        Strafe left / right
    Mouse move   Look / rotate (mouse-look, like a modern FPS)
    Left Click   Sword attack (close range)
    Right Click  Ranged attack (costs mana)
    1 / 2        Switch ranged ability (Arcane Bolt / Fire Orb)
    E            Interact (open treasure chests)
    M            Toggle minimap
    R            Return to last checkpoint (also respawns you after death)
    ENTER        Start / restart game
    ESC          Quit
"""

import sys
import math
import random

from OpenGL.GL import *
from OpenGL.GLU import *
from OpenGL.GLUT import *

# ==========================================================================
# WINDOW / GLOBAL STATE
# ==========================================================================
WIN_W, WIN_H = 1100, 800
quad = None

game_state = "menu"          # menu | playing | dead | won
camera_mode = "third"        # third | first
minimap_on = True
mouse_locked = False

keys_pressed = set()
last_tick_ms = 0
sim_time = 0.0

message_text = ""
message_timer = 0.0
flash_timer = 0.0          # red damage flash
heal_flash_timer = 0.0     # green heal flash
win_timer = 0.0

REQUIRED_KEYS = 2

# ==========================================================================
# LEVEL LAYOUT  (rectangles are (xmin, xmax, zmin, zmax))
# ==========================================================================
ROOM_START    = (-8, 8, 0, 20)
CORR1         = (-3, 3, -15, 0)
ROOM2         = (-10, 10, -45, -15)
BRANCH_CORR   = (10, 25, -35, -25)
ROOM_TREASURE = (25, 45, -40, -20)
GATE_CORR     = (-3, 3, -55, -45)
ROOM_BOSS     = (-15, 15, -95, -55)
EXIT_ZONE     = (-4, 4, -95, -90)

WALL_H = 8.0

COL_START = (0.42, 0.40, 0.46)
COL_ROOM2 = (0.30, 0.28, 0.34)
COL_TREAS = (0.55, 0.47, 0.28)
COL_BOSS  = (0.35, 0.16, 0.18)
COL_CORR  = (0.22, 0.21, 0.26)


def _w(cx, cz, sx, sz, col):
    return (cx, cz, sx, sz, col[0], col[1], col[2])


WALLS = [
    # Start room
    _w(-8, 10, 1, 20, COL_START),
    _w(8, 10, 1, 20, COL_START),
    _w(0, 20, 16, 1, COL_START),
    _w(-5.5, 0, 5, 1, COL_START),
    _w(5.5, 0, 5, 1, COL_START),
    # Corridor 1
    _w(-3, -7.5, 1, 15, COL_CORR),
    _w(3, -7.5, 1, 15, COL_CORR),
    # Room 2
    _w(-10, -30, 1, 30, COL_ROOM2),
    _w(-6.5, -15, 7, 1, COL_ROOM2),
    _w(6.5, -15, 7, 1, COL_ROOM2),
    _w(-6.5, -45, 7, 1, COL_ROOM2),
    _w(6.5, -45, 7, 1, COL_ROOM2),
    _w(10, -40, 1, 10, COL_ROOM2),
    _w(10, -20, 1, 10, COL_ROOM2),
    # Branch corridor
    _w(17.5, -25, 15, 1, COL_CORR),
    _w(17.5, -35, 15, 1, COL_CORR),
    # Treasure room
    _w(45, -30, 1, 20, COL_TREAS),
    _w(35, -20, 20, 1, COL_TREAS),
    _w(35, -40, 20, 1, COL_TREAS),
    _w(25, -37.5, 1, 5, COL_TREAS),
    _w(25, -22.5, 1, 5, COL_TREAS),
    # Gate corridor
    _w(-3, -50, 1, 10, COL_CORR),
    _w(3, -50, 1, 10, COL_CORR),
    # Boss room
    _w(-15, -75, 1, 40, COL_BOSS),
    _w(15, -75, 1, 40, COL_BOSS),
    _w(-9, -55, 12, 1, COL_BOSS),
    _w(9, -55, 12, 1, COL_BOSS),
    _w(-9.5, -95, 11, 1, COL_BOSS),
    _w(9.5, -95, 11, 1, COL_BOSS),
]

FLOORS = [
    (ROOM_START, (0.20, 0.19, 0.24)),
    (CORR1, (0.15, 0.14, 0.18)),
    (ROOM2, (0.16, 0.15, 0.19)),
    (BRANCH_CORR, (0.15, 0.14, 0.18)),
    (ROOM_TREASURE, (0.30, 0.25, 0.14)),
    (GATE_CORR, (0.15, 0.14, 0.18)),
    (ROOM_BOSS, (0.22, 0.10, 0.11)),
]

# Dynamic gates: cx, cz, sx, sz, locked flag, open animation progress (0..1)
gate_door = {"cx": 0.0, "cz": -50.0, "sx": 6.0, "sz": 1.0, "locked": True, "progress": 0.0}
exit_door = {"cx": 0.0, "cz": -95.0, "sx": 8.0, "sz": 1.0, "locked": True, "progress": 0.0}

# ==========================================================================
# ENTITY TEMPLATES
# ==========================================================================
MONSTER_TYPES = {
    "fast":   dict(radius=0.45, height=1.3, speed=5.5, health=35, dmg=8,
                   atk_range=1.4, atk_cd=0.8, detect=14, color=(0.45, 0.75, 0.30), score=10),
    "melee":  dict(radius=0.65, height=1.8, speed=3.0, health=75, dmg=18,
                   atk_range=1.9, atk_cd=1.2, detect=12, color=(0.50, 0.30, 0.22), score=25),
    "ranged": dict(radius=0.55, height=1.6, speed=2.4, health=40, dmg=10,
                   atk_range=15.0, atk_cd=1.8, detect=16, color=(0.55, 0.55, 0.68), score=20),
}

RANGED_ABILITIES = {
    1: dict(name="Arcane Bolt", cost=10, dmg=15, speed=22.0, color=(0.35, 0.55, 1.0), cd=0.35),
    2: dict(name="Fire Orb",    cost=18, dmg=24, speed=15.0, color=(1.0, 0.45, 0.15), cd=0.55),
}

# ==========================================================================
# GAME OBJECTS (rebuilt on init_level)
# ==========================================================================
player = {}
monsters = []
boss = {}
projectiles = []
pickups = []
traps = []
particles = []
dust = []


def point_in_rect(x, z, r, margin=0.0):
    return (r[0] + margin) <= x <= (r[1] - margin) and (r[2] + margin) <= z <= (r[3] - margin)


def new_monster(mtype, x, z, room):
    t = MONSTER_TYPES[mtype]
    return dict(type=mtype, x=x, z=z, angle=random.uniform(0, 360),
                health=t["health"], max_health=t["health"], alive=True,
                state="patrol", room=room, patrol_x=x, patrol_z=z,
                detect_timer=0.0, atk_cd=random.uniform(0, 0.5), death_timer=0.0,
                hit_flash=0.0)


def init_level():
    global player, monsters, boss, projectiles, pickups, traps, particles, dust
    global message_text, message_timer, flash_timer, win_timer

    player = dict(
        x=0.0, y=0.0, z=15.0, angle=180.0,
        health=100.0, max_health=100.0,
        mana=50.0, max_mana=50.0,
        speed=7.0, radius=0.55,
        keys=0, treasure=0, score=0,
        sword_cd=0.0, ranged_cd=0.0, ranged_type=1,
        invuln=0.0, alive=True,
        checkpoint=(0.0, 15.0),
        sword_anim=0.0,
    )

    monsters = [
        new_monster("fast", -4, 12, ROOM_START),
        new_monster("fast", 4, 8, ROOM_START),
        new_monster("melee", -5, -25, ROOM2),
        new_monster("ranged", 6, -38, ROOM2),
        new_monster("melee", 30, -25, ROOM_TREASURE),
    ]

    boss = dict(x=0.0, z=-80.0, angle=0.0,
                health=420.0, max_health=420.0, alive=True,
                state="dormant", atk_cd=0.0, mode="melee",
                telegraph=0.0, enraged=False, death_timer=0.0, hit_flash=0.0)

    projectiles = []
    particles = []

    pickups = [
        dict(type="key", x=0, z=17, taken=False, phase=0.0),
        dict(type="potion_h", x=-6, z=6, taken=False, phase=1.1),
        dict(type="potion_h", x=-3, z=-35, taken=False, phase=2.0),
        dict(type="potion_mana", x=8, z=-40, taken=False, phase=0.6),
        dict(type="key", x=40, z=-25, taken=False, phase=1.7),
        dict(type="potion_mana", x=30, z=-35, taken=False, phase=2.4),
        dict(type="chest", x=38, z=-22, taken=False, phase=0.0),
        dict(type="chest", x=42, z=-33, taken=False, phase=0.9),
        dict(type="chest", x=28, z=-37, taken=False, phase=1.5),
        dict(type="potion_h", x=0, z=-88, taken=False, phase=3.0),
    ]

    traps = [
        dict(x=0, z=-7.5, radius=1.6, period=2.0, phase=0.0, cd=0.0),
        dict(x=0, z=-50, radius=1.4, period=1.6, phase=0.5, cd=0.0),
    ]

    dust = [dict(x=random.uniform(-14, 44), y=random.uniform(0.5, 6.5),
                 z=random.uniform(-93, 19), speed=random.uniform(0.15, 0.4))
            for _ in range(140)]

    gate_door["locked"] = True
    gate_door["progress"] = 0.0
    exit_door["locked"] = True
    exit_door["progress"] = 0.0

    message_text = ""
    message_timer = 0.0
    flash_timer = 0.0
    win_timer = 0.0


# ==========================================================================
# SMALL HELPERS
# ==========================================================================
def dist2d(x1, z1, x2, z2):
    return math.hypot(x1 - x2, z1 - z2)


def show_message(text, dur=2.2):
    global message_text, message_timer
    message_text = text
    message_timer = dur


def spawn_particles(x, y, z, color, n=10):
    for _ in range(n):
        particles.append(dict(
            x=x, y=y, z=z,
            vx=random.uniform(-2.2, 2.2), vy=random.uniform(1.0, 4.0), vz=random.uniform(-2.2, 2.2),
            life=random.uniform(0.35, 0.7), color=color, size=random.uniform(0.08, 0.18)
        ))


def damage_player(amount):
    global flash_timer, game_state
    if not player.get("alive", False) or player["invuln"] > 0 or game_state != "playing":
        return
    player["health"] -= amount
    player["invuln"] = 0.5
    flash_timer = 0.5
    spawn_particles(player["x"], 1.2, player["z"], (0.9, 0.15, 0.15), 8)
    if player["health"] <= 0:
        player["health"] = 0
        player["alive"] = False
        game_state = "dead"
        try:
            glutSetCursor(GLUT_CURSOR_INHERIT)
        except Exception:
            pass


def heal_player(amount, is_mana=False):
    global heal_flash_timer
    if is_mana:
        player["mana"] = min(player["max_mana"], player["mana"] + amount)
    else:
        player["health"] = min(player["max_health"], player["health"] + amount)
    heal_flash_timer = 0.4


def resolve_wall_collisions(x, z, radius, walls):
    for (cx, cz, sx, sz, r, g, b) in walls:
        hx, hz = sx / 2.0, sz / 2.0
        closest_x = max(cx - hx, min(x, cx + hx))
        closest_z = max(cz - hz, min(z, cz + hz))
        dx, dz = x - closest_x, z - closest_z
        dist2 = dx * dx + dz * dz
        if dist2 < radius * radius:
            dist = math.sqrt(dist2) if dist2 > 1e-6 else 0.001
            overlap = radius - dist
            nx = dx / dist if dist > 1e-6 else 1.0
            nz = dz / dist if dist > 1e-6 else 0.0
            x += nx * overlap
            z += nz * overlap
    return x, z


def active_walls():
    w = list(WALLS)
    if gate_door["progress"] < 1.0:
        w.append((gate_door["cx"], gate_door["cz"], gate_door["sx"], gate_door["sz"], 0.6, 0.15, 0.1))
    if exit_door["progress"] < 1.0:
        w.append((exit_door["cx"], exit_door["cz"], exit_door["sx"], exit_door["sz"], 0.6, 0.5, 0.1))
    return w


print("Module part 1 loaded OK" if __name__ != "__complete__" else "", file=sys.stderr) if False else None

# ==========================================================================
# UPDATE: PLAYER
# ==========================================================================
def update_player(dt):
    global game_state
    if not player["alive"] or game_state != "playing":
        return

    rad = math.radians(player["angle"])
    fx, fz = math.sin(rad), -math.cos(rad)
    rx, rz = math.cos(rad), math.sin(rad)

    mx, mz = 0.0, 0.0
    if b'w' in keys_pressed:
        mx += fx; mz += fz
    if b's' in keys_pressed:
        mx -= fx; mz -= fz
    if b'd' in keys_pressed:
        mx += rx; mz += rz
    if b'a' in keys_pressed:
        mx -= rx; mz -= rz

    mlen = math.hypot(mx, mz)
    if mlen > 1e-6:
        mx /= mlen; mz /= mlen
        nx = player["x"] + mx * player["speed"] * dt
        nz = player["z"] + mz * player["speed"] * dt
        nx, nz = resolve_wall_collisions(nx, nz, player["radius"], active_walls())
        player["x"], player["z"] = nx, nz

    if player["invuln"] > 0:
        player["invuln"] -= dt
    if player["sword_cd"] > 0:
        player["sword_cd"] -= dt
    if player["ranged_cd"] > 0:
        player["ranged_cd"] -= dt
    if player["sword_anim"] > 0:
        player["sword_anim"] -= dt

    # mana regen
    player["mana"] = min(player["max_mana"], player["mana"] + 3.0 * dt)

    # checkpoints
    if point_in_rect(player["x"], player["z"], ROOM2, -2) and player["z"] <= -15:
        player["checkpoint"] = (0.0, -18.0)
    if not gate_door["locked"] and point_in_rect(player["x"], player["z"], ROOM_BOSS, -2):
        player["checkpoint"] = (0.0, -60.0)
        if boss["state"] == "dormant":
            boss["state"] = "idle"
            show_message("The Dungeon Boss awakens!", 2.5)

    # gate unlock check
    if gate_door["locked"] and player["keys"] >= REQUIRED_KEYS:
        gate_door["locked"] = False
        show_message("Gate Unlocked! The path to the boss is open.", 2.5)
        spawn_particles(gate_door["cx"], 3.0, gate_door["cz"], (0.9, 0.8, 0.2), 20)

    # exit unlock check
    if exit_door["locked"] and not boss["alive"]:
        exit_door["locked"] = False
        show_message("The boss falls! The exit is open!", 2.5)
        spawn_particles(exit_door["cx"], 3.0, exit_door["cz"], (0.3, 1.0, 0.4), 24)

    # win check
    if not exit_door["locked"] and point_in_rect(player["x"], player["z"], EXIT_ZONE, -0.2):
        game_state = "won"
        try:
            glutSetCursor(GLUT_CURSOR_INHERIT)
        except Exception:
            pass

    # pickups (auto-collect keys/potions, chests need E)
    for p in pickups:
        if p["taken"]:
            continue
        if p["type"] == "chest":
            continue
        if dist2d(player["x"], player["z"], p["x"], p["z"]) < 1.2:
            p["taken"] = True
            if p["type"] == "key":
                player["keys"] += 1
                player["score"] += 20
                show_message("Key collected! (%d/%d)" % (player["keys"], REQUIRED_KEYS))
            elif p["type"] == "potion_h":
                heal_player(35, is_mana=False)
                player["score"] += 5
                show_message("Health Potion +35")
            elif p["type"] == "potion_mana":
                heal_player(25, is_mana=True)
                player["score"] += 5
                show_message("Mana Potion +25")
            spawn_particles(p["x"], 1.0, p["z"], (0.9, 0.85, 0.3), 10)

    # traps
    for t in traps:
        t["cd"] = max(0.0, t["cd"] - dt)
        active = (math.sin(sim_time * (2 * math.pi / t["period"]) + t["phase"] * 6.28) > 0.2)
        if active and t["cd"] <= 0 and dist2d(player["x"], player["z"], t["x"], t["z"]) < t["radius"]:
            damage_player(12)
            t["cd"] = 0.6


def gate_door_and_exit_update(dt):
    for door in (gate_door, exit_door):
        if not door["locked"] and door["progress"] < 1.0:
            door["progress"] = min(1.0, door["progress"] + dt / 1.2)


# ==========================================================================
# UPDATE: MONSTER AI  (idle/patrol -> detect -> chase -> attack)
# ==========================================================================
def update_monster_ai(m, dt):
    if not m["alive"]:
        m["death_timer"] += dt
        return
    if m["hit_flash"] > 0:
        m["hit_flash"] -= dt

    t = MONSTER_TYPES[m["type"]]
    dp = dist2d(m["x"], m["z"], player["x"], player["z"]) if player["alive"] else 9999

    if m["state"] == "patrol":
        d = dist2d(m["x"], m["z"], m["patrol_x"], m["patrol_z"])
        if d < 0.4:
            room = m["room"]
            m["patrol_x"] = random.uniform(room[0] + 2, room[1] - 2)
            m["patrol_z"] = random.uniform(room[2] + 2, room[3] - 2)
        else:
            ang = math.atan2(m["patrol_x"] - m["x"], -(m["patrol_z"] - m["z"]))
            m["angle"] = math.degrees(ang)
            spd = t["speed"] * 0.35
            nx = m["x"] + math.sin(ang) * spd * dt
            nz = m["z"] - math.cos(ang) * spd * dt
            nx, nz = resolve_wall_collisions(nx, nz, t["radius"], active_walls())
            m["x"], m["z"] = nx, nz
        if player["alive"] and dp < t["detect"]:
            m["state"] = "detect"
            m["detect_timer"] = 0.4

    elif m["state"] == "detect":
        m["detect_timer"] -= dt
        if m["detect_timer"] <= 0:
            m["state"] = "chase"

    elif m["state"] == "chase":
        if not player["alive"]:
            m["state"] = "patrol"
        elif dp > t["detect"] * 1.6:
            m["state"] = "patrol"
        elif dp <= t["atk_range"]:
            m["state"] = "attack"
        else:
            ang = math.atan2(player["x"] - m["x"], -(player["z"] - m["z"]))
            m["angle"] = math.degrees(ang)
            nx = m["x"] + math.sin(ang) * t["speed"] * dt
            nz = m["z"] - math.cos(ang) * t["speed"] * dt
            nx, nz = resolve_wall_collisions(nx, nz, t["radius"], active_walls())
            m["x"], m["z"] = nx, nz

    elif m["state"] == "attack":
        if not player["alive"] or dp > t["atk_range"] * 1.3:
            m["state"] = "chase"
        else:
            ang = math.atan2(player["x"] - m["x"], -(player["z"] - m["z"]))
            m["angle"] = math.degrees(ang)
            m["atk_cd"] -= dt
            if m["atk_cd"] <= 0:
                m["atk_cd"] = t["atk_cd"]
                if m["type"] == "ranged":
                    spawn_projectile(m["x"], 1.2, m["z"], player["x"], 1.0, player["z"],
                                      speed=13.0, dmg=t["dmg"], owner="enemy",
                                      color=(0.6, 0.9, 1.0))
                else:
                    damage_player(t["dmg"])


def spawn_projectile(x, y, z, tx, ty, tz, speed, dmg, owner, color, radius=0.22):
    dx, dy, dz = tx - x, ty - y, tz - z
    length = math.sqrt(dx * dx + dy * dy + dz * dz) or 1.0
    projectiles.append(dict(x=x, y=y, z=z, dx=dx / length, dy=dy / length, dz=dz / length,
                             speed=speed, dmg=dmg, owner=owner, color=color, life=4.0, radius=radius))


def update_projectiles(dt):
    for p in projectiles[:]:
        p["x"] += p["dx"] * p["speed"] * dt
        p["y"] += p["dy"] * p["speed"] * dt
        p["z"] += p["dz"] * p["speed"] * dt
        p["life"] -= dt

        hit = False
        if p["life"] <= 0:
            hit = True
        else:
            for (cx, cz, sx, sz, r, g, b) in active_walls():
                if (cx - sx / 2 <= p["x"] <= cx + sx / 2) and (cz - sz / 2 <= p["z"] <= cz + sz / 2):
                    hit = True
                    spawn_particles(p["x"], p["y"], p["z"], p["color"], 5)
                    break

        if not hit:
            if p["owner"] == "player":
                for m in monsters:
                    if m["alive"] and dist2d(p["x"], p["z"], m["x"], m["z"]) < (0.6 + p["radius"]):
                        hit_monster(m, p["dmg"])
                        spawn_particles(p["x"], p["y"], p["z"], p["color"], 8)
                        hit = True
                        break
                if not hit and boss["alive"] and dist2d(p["x"], p["z"], boss["x"], boss["z"]) < (1.9 + p["radius"]):
                    hit_boss(p["dmg"])
                    spawn_particles(p["x"], p["y"], p["z"], p["color"], 10)
                    hit = True
            elif p["owner"] == "enemy":
                if player["alive"] and dist2d(p["x"], p["z"], player["x"], player["z"]) < (player["radius"] + p["radius"]):
                    damage_player(p["dmg"])
                    hit = True

        if hit:
            projectiles.remove(p)


def hit_monster(m, dmg):
    m["health"] -= dmg
    m["hit_flash"] = 0.15
    if m["health"] <= 0 and m["alive"]:
        m["alive"] = False
        m["death_timer"] = 0.0
        player["score"] += MONSTER_TYPES[m["type"]]["score"]
        show_message("%s defeated! +%d" % (m["type"].capitalize(), MONSTER_TYPES[m["type"]]["score"]), 1.2)
        spawn_particles(m["x"], 1.0, m["z"], MONSTER_TYPES[m["type"]]["color"], 16)


def hit_boss(dmg):
    if not boss["alive"]:
        return
    boss["health"] -= dmg
    boss["hit_flash"] = 0.15
    spawn_particles(boss["x"], 2.2, boss["z"], (1.0, 0.3, 0.3), 6)
    if boss["health"] <= 0:
        boss["alive"] = False
        boss["health"] = 0
        player["score"] += 500
        show_message("THE BOSS HAS FALLEN!", 3.0)
        spawn_particles(boss["x"], 2.0, boss["z"], (1.0, 0.6, 0.1), 40)


# ==========================================================================
# UPDATE: BOSS AI
# ==========================================================================
def update_boss(dt):
    if not boss["alive"]:
        boss["death_timer"] += dt
        return
    if boss["hit_flash"] > 0:
        boss["hit_flash"] -= dt

    if boss["health"] < boss["max_health"] * 0.3 and not boss["enraged"]:
        boss["enraged"] = True
        show_message("The Boss enters a FRENZY!", 2.0)

    if boss["state"] == "dormant":
        return

    dp = dist2d(boss["x"], boss["z"], player["x"], player["z"]) if player["alive"] else 9999
    speed = 3.0 * (1.4 if boss["enraged"] else 1.0)
    melee_range = 3.6
    ang = math.atan2(player["x"] - boss["x"], -(player["z"] - boss["z"])) if player["alive"] else 0
    boss["angle"] = math.degrees(ang)

    if boss["state"] == "idle":
        boss["state"] = "chase"

    elif boss["state"] == "chase":
        if not player["alive"]:
            return
        if dp <= melee_range:
            boss["state"] = "telegraph"
            boss["mode"] = "melee"
            boss["telegraph"] = 0.55
        elif dp < 20 and boss["atk_cd"] <= 0:
            boss["state"] = "telegraph"
            boss["mode"] = "ranged"
            boss["telegraph"] = 0.5
        else:
            nx = boss["x"] + math.sin(ang) * speed * dt
            nz = boss["z"] - math.cos(ang) * speed * dt
            nx, nz = resolve_wall_collisions(nx, nz, 1.8, active_walls())
            boss["x"], boss["z"] = nx, nz
        boss["atk_cd"] = max(0.0, boss["atk_cd"] - dt)

    elif boss["state"] == "telegraph":
        boss["telegraph"] -= dt
        if boss["telegraph"] <= 0:
            dmg_mult = 1.3 if boss["enraged"] else 1.0
            if boss["mode"] == "melee":
                if player["alive"] and dist2d(boss["x"], boss["z"], player["x"], player["z"]) <= melee_range + 1.0:
                    damage_player(30 * dmg_mult)
                boss["atk_cd"] = 1.0
            else:
                for offs in (-14, 0, 14):
                    a2 = ang + math.radians(offs)
                    tx = boss["x"] + math.sin(a2) * 10
                    tz = boss["z"] - math.cos(a2) * 10
                    spawn_projectile(boss["x"], 1.6, boss["z"], tx, 1.0, tz,
                                      speed=11.0, dmg=20 * dmg_mult, owner="enemy",
                                      color=(1.0, 0.35, 0.1), radius=0.35)
                boss["atk_cd"] = 1.6
            boss["state"] = "chase"


# ==========================================================================
# UPDATE: PARTICLES / DUST
# ==========================================================================
def update_particles(dt):
    for p in particles[:]:
        p["x"] += p["vx"] * dt
        p["y"] += p["vy"] * dt
        p["z"] += p["vz"] * dt
        p["vy"] -= 6.0 * dt
        p["life"] -= dt
        if p["life"] <= 0:
            particles.remove(p)


def update_dust(dt):
    for d in dust:
        d["y"] += d["speed"] * dt
        if d["y"] > 7.0:
            d["y"] = 0.3


# ==========================================================================
# MAIN UPDATE TICK
# ==========================================================================
def update_world(dt):
    global sim_time, message_timer, flash_timer, heal_flash_timer, win_timer

    sim_time += dt
    if message_timer > 0:
        message_timer -= dt
    if flash_timer > 0:
        flash_timer -= dt
    if heal_flash_timer > 0:
        heal_flash_timer -= dt

    if game_state != "playing":
        update_dust(dt)
        if game_state == "won":
            win_timer += dt
        return

    update_player(dt)
    gate_door_and_exit_update(dt)
    for m in monsters:
        update_monster_ai(m, dt)
    update_boss(dt)
    update_projectiles(dt)
    update_particles(dt)
    update_dust(dt)


# ==========================================================================
# COMBAT ACTIONS (player)
# ==========================================================================
def player_sword_attack():
    if not player["alive"] or game_state != "playing" or player["sword_cd"] > 0:
        return
    player["sword_cd"] = 0.4
    player["sword_anim"] = 0.25
    rad = math.radians(player["angle"])
    fx, fz = math.sin(rad), -math.cos(rad)
    hit_any = False
    for m in monsters:
        if not m["alive"]:
            continue
        dx, dz = m["x"] - player["x"], m["z"] - player["z"]
        d = math.hypot(dx, dz)
        if d < 2.6:
            dot = (dx / d * fx + dz / d * fz) if d > 1e-5 else 1.0
            if dot > 0.35:
                hit_monster(m, 28)
                hit_any = True
    if boss["alive"]:
        dx, dz = boss["x"] - player["x"], boss["z"] - player["z"]
        d = math.hypot(dx, dz)
        if d < 3.2:
            dot = (dx / d * fx + dz / d * fz) if d > 1e-5 else 1.0
            if dot > 0.35:
                hit_boss(28)
                hit_any = True
    if not hit_any:
        spawn_particles(player["x"] + fx * 1.4, 1.0, player["z"] + fz * 1.4, (0.8, 0.8, 0.9), 4)


def player_ranged_attack():
    if not player["alive"] or game_state != "playing" or player["ranged_cd"] > 0:
        return
    ability = RANGED_ABILITIES[player["ranged_type"]]
    if player["mana"] < ability["cost"]:
        show_message("Not enough mana!", 1.0)
        return
    player["mana"] -= ability["cost"]
    player["ranged_cd"] = ability["cd"]
    rad = math.radians(player["angle"])
    fx, fz = math.sin(rad), -math.cos(rad)
    spawn_projectile(player["x"] + fx, 1.2, player["z"] + fz,
                      player["x"] + fx * 20, 1.2, player["z"] + fz * 20,
                      speed=ability["speed"], dmg=ability["dmg"], owner="player", color=ability["color"])


def player_interact():
    if not player["alive"] or game_state != "playing":
        return
    for p in pickups:
        if p["taken"] or p["type"] != "chest":
            continue
        if dist2d(player["x"], player["z"], p["x"], p["z"]) < 1.8:
            p["taken"] = True
            player["treasure"] += 1
            player["score"] += 50
            show_message("Treasure chest opened! +50")
            spawn_particles(p["x"], 1.0, p["z"], (1.0, 0.85, 0.2), 16)
            return


def player_checkpoint():
    if game_state == "dead":
        respawn_player()
    elif game_state == "playing" and player["alive"]:
        cx, cz = player["checkpoint"]
        player["x"], player["z"] = cx, cz
        player["invuln"] = 0.6
        show_message("Returned to checkpoint")


def respawn_player():
    global game_state
    cx, cz = player["checkpoint"]
    player["x"], player["z"] = cx, cz
    player["health"] = player["max_health"] * 0.6
    player["mana"] = player["max_mana"]
    player["alive"] = True
    player["invuln"] = 1.5
    game_state = "playing"
    try:
        glutSetCursor(GLUT_CURSOR_NONE)
    except Exception:
        pass
    show_message("Respawned at checkpoint")


# ==========================================================================
# DRAW PRIMITIVES
# ==========================================================================
def draw_box(cx, cy, cz, sx, sy, sz, color):
    glPushMatrix()
    glTranslatef(cx, cy, cz)
    glScalef(sx, sy, sz)
    glColor3f(*color)
    glutSolidCube(1.0)
    glPopMatrix()


def draw_sphere(cx, cy, cz, radius, color, slices=14, stacks=14):
    glPushMatrix()
    glTranslatef(cx, cy, cz)
    glColor3f(*color)
    glutSolidSphere(radius, slices, stacks)
    glPopMatrix()


def draw_cylinder(cx, cy, cz, radius, height, color, top_radius=None, slices=12):
    if top_radius is None:
        top_radius = radius
    glPushMatrix()
    glTranslatef(cx, cy, cz)
    glColor3f(*color)
    glRotatef(-90, 1, 0, 0)
    gluCylinder(quad, radius, top_radius, height, slices, 4)
    glPopMatrix()


def draw_cone(cx, cy, cz, radius, height, color, slices=10):
    glPushMatrix()
    glTranslatef(cx, cy, cz)
    glColor3f(*color)
    glRotatef(-90, 1, 0, 0)
    glutSolidCone(radius, height, slices, 4)
    glPopMatrix()


def draw_flat_ring(cx, cy, cz, radius, color, alpha):
    glPushMatrix()
    glTranslatef(cx, cy, cz)
    glDisable(GL_LIGHTING)
    glEnable(GL_BLEND)
    glBlendFunc(GL_SRC_ALPHA, GL_ONE)
    glColor4f(color[0], color[1], color[2], alpha)
    glBegin(GL_TRIANGLE_FAN)
    glVertex3f(0, 0, 0)
    for i in range(25):
        a = 2 * math.pi * i / 24
        glVertex3f(math.cos(a) * radius, 0, math.sin(a) * radius)
    glEnd()
    glDisable(GL_BLEND)
    glEnable(GL_LIGHTING)
    glPopMatrix()


def draw_health_bar_world(x, y, z, frac, width=1.2):
    glDisable(GL_LIGHTING)
    glDisable(GL_DEPTH_TEST)
    frac = max(0.0, min(1.0, frac))
    glPushMatrix()
    glTranslatef(x, y, z)
    glColor3f(0.15, 0.05, 0.05)
    glBegin(GL_QUADS)
    glVertex3f(-width / 2, 0, 0); glVertex3f(width / 2, 0, 0)
    glVertex3f(width / 2, 0.14, 0); glVertex3f(-width / 2, 0.14, 0)
    glEnd()
    if frac > 0.5:
        glColor3f(0.2, 0.9, 0.25)
    elif frac > 0.25:
        glColor3f(0.9, 0.7, 0.1)
    else:
        glColor3f(0.9, 0.15, 0.15)
    w = width * frac
    glBegin(GL_QUADS)
    glVertex3f(-width / 2, 0, 0.001); glVertex3f(-width / 2 + w, 0, 0.001)
    glVertex3f(-width / 2 + w, 0.14, 0.001); glVertex3f(-width / 2, 0.14, 0.001)
    glEnd()
    glPopMatrix()
    glEnable(GL_DEPTH_TEST)
    glEnable(GL_LIGHTING)


# ==========================================================================
# DRAW: WORLD GEOMETRY
# ==========================================================================
def draw_level_static():
    for (rect, color) in FLOORS:
        cx, cz = (rect[0] + rect[1]) / 2.0, (rect[2] + rect[3]) / 2.0
        sx, sz = rect[1] - rect[0], rect[3] - rect[2]
        draw_box(cx, -0.05, cz, sx, 0.1, sz, color)
        draw_box(cx, WALL_H, cz, sx, 0.1, sz, (0.05, 0.04, 0.06))

    for (cx, cz, sx, sz, r, g, b) in WALLS:
        draw_box(cx, WALL_H / 2, cz, sx, WALL_H, sz, (r, g, b))

    for door in (gate_door, exit_door):
        h = WALL_H * (1.0 - door["progress"])
        if h > 0.05:
            glow = 0.5 + 0.3 * math.sin(sim_time * 4)
            col = (0.55 + glow * 0.2, 0.12, 0.1) if door["locked"] else (0.2, 0.5, 0.2)
            draw_box(door["cx"], h / 2, door["cz"], door["sx"], h, door["sz"], col)


def draw_traps():
    for t in traps:
        active = (math.sin(sim_time * (2 * math.pi / t["period"]) + t["phase"] * 6.28) > 0.2)
        base_col = (0.5, 0.15, 0.15) if active else (0.35, 0.32, 0.3)
        draw_cylinder(t["x"], 0.02, t["z"], t["radius"], 0.05, base_col, slices=16)
        n_spikes = 6
        spike_h = 0.9 if active else 0.05
        for i in range(n_spikes):
            a = 2 * math.pi * i / n_spikes
            sx = t["x"] + math.cos(a) * t["radius"] * 0.55
            sz = t["z"] + math.sin(a) * t["radius"] * 0.55
            draw_cone(sx, 0.0, sz, 0.12, spike_h, (0.55, 0.55, 0.6))


def draw_pickups():
    for p in pickups:
        if p["taken"]:
            continue
        bob = math.sin(sim_time * 2.2 + p["phase"] * 6.28) * 0.15
        spin = (sim_time * 60 + p["phase"] * 300) % 360
        glPushMatrix()
        glTranslatef(p["x"], 1.0 + bob, p["z"])
        glRotatef(spin, 0, 1, 0)
        if p["type"] == "key":
            glColor3f(1.0, 0.85, 0.2)
            draw_cylinder(0, 0, 0, 0.12, 0.5, (1.0, 0.85, 0.2), slices=8)
            draw_sphere(0, -0.28, 0, 0.22, (1.0, 0.85, 0.2), 10, 10)
        elif p["type"] == "potion_h":
            draw_sphere(0, 0, 0, 0.25, (0.85, 0.1, 0.15), 10, 10)
            draw_cylinder(0, 0.2, 0, 0.08, 0.15, (0.7, 0.7, 0.75), slices=8)
        elif p["type"] == "potion_mana":
            draw_sphere(0, 0, 0, 0.25, (0.15, 0.35, 0.95), 10, 10)
            draw_cylinder(0, 0.2, 0, 0.08, 0.15, (0.7, 0.7, 0.75), slices=8)
        elif p["type"] == "chest":
            glPopMatrix()
            draw_box(p["x"], 0.35, p["z"], 1.0, 0.7, 0.7, (0.45, 0.28, 0.12))
            draw_box(p["x"], 0.72, p["z"], 1.02, 0.15, 0.72, (0.75, 0.6, 0.15))
            continue
        glPopMatrix()


# ==========================================================================
# DRAW: CHARACTERS
# ==========================================================================
def draw_player_model():
    if camera_mode != "third" or not player["alive"]:
        return
    glPushMatrix()
    glTranslatef(player["x"], 0, player["z"])
    glRotatef(player["angle"], 0, 1, 0)

    flash = player["invuln"] > 0 and int(sim_time * 12) % 2 == 0
    body_col = (0.75, 0.75, 0.8) if flash else (0.25, 0.32, 0.42)

    draw_cylinder(-0.22, 0.0, 0, 0.13, 0.85, (0.15, 0.15, 0.2))
    draw_cylinder(0.22, 0.0, 0, 0.13, 0.85, (0.15, 0.15, 0.2))
    draw_cylinder(0, 0.85, 0, 0.32, 0.65, body_col, top_radius=0.26)
    draw_cone(0, 0.7, -0.05, 0.5, 0.9, (0.15, 0.12, 0.18))
    draw_sphere(0, 1.65, 0, 0.24, (0.85, 0.7, 0.55))
    draw_cone(0, 1.85, 0, 0.27, 0.35, (0.3, 0.15, 0.5))

    swing = math.sin(min(1.0, (0.25 - player["sword_anim"]) / 0.25) * math.pi) if player["sword_anim"] > 0 else 0
    glPushMatrix()
    glTranslatef(0.35, 1.3, 0.1)
    glRotatef(-30 - swing * 90, 0, 1, 0)
    draw_cylinder(0, 0, 0, 0.06, 0.9, (0.8, 0.8, 0.85))
    glPopMatrix()
    glPopMatrix()


def draw_monster(m):
    t = MONSTER_TYPES[m["type"]]
    if not m["alive"]:
        if m["death_timer"] > 0.6:
            return
        sink = m["death_timer"] / 0.6
        glPushMatrix()
        glTranslatef(m["x"], -sink * 1.2, m["z"])
        glRotatef(m["angle"], 0, 1, 0)
        glRotatef(sink * 80, 1, 0, 0)
        draw_sphere(0, t["height"], 0, t["radius"] * 0.8, (0.2, 0.2, 0.2))
        glPopMatrix()
        return

    col = (1.0, 1.0, 1.0) if m["hit_flash"] > 0 else t["color"]
    glPushMatrix()
    glTranslatef(m["x"], 0, m["z"])
    glRotatef(m["angle"], 0, 1, 0)

    if m["type"] == "fast":
        draw_cylinder(0, 0, 0, t["radius"] * 0.7, t["height"] * 0.75, col)
        draw_sphere(0, t["height"] * 0.85, 0, t["radius"] * 0.9, col, 10, 10)
        draw_sphere(-0.12, t["height"] * 0.9, 0.25, 0.06, (1, 0.2, 0.1))
        draw_sphere(0.12, t["height"] * 0.9, 0.25, 0.06, (1, 0.2, 0.1))
    elif m["type"] == "melee":
        draw_cylinder(0, 0, 0, t["radius"], t["height"] * 0.7, col, top_radius=t["radius"] * 1.2)
        draw_sphere(0, t["height"] * 0.85, 0, t["radius"] * 0.85, col, 10, 10)
        draw_cone(-0.15, t["height"] * 1.0, 0, 0.08, 0.25, (0.9, 0.9, 0.85))
        draw_cone(0.15, t["height"] * 1.0, 0, 0.08, 0.25, (0.9, 0.9, 0.85))
        draw_cylinder(t["radius"] * 1.1, t["height"] * 0.55, 0, 0.1, 0.9, (0.5, 0.5, 0.55))
    else:  # ranged
        draw_cylinder(0, 0, 0, t["radius"] * 0.6, t["height"] * 0.8, col)
        draw_sphere(0, t["height"] * 0.92, 0, t["radius"] * 0.75, col, 10, 10)
        draw_sphere(-0.1, t["height"] * 0.95, 0.22, 0.05, (0.9, 0.85, 0.2))
        draw_sphere(0.1, t["height"] * 0.95, 0.22, 0.05, (0.9, 0.85, 0.2))

    glPopMatrix()
    draw_health_bar_world(m["x"], t["height"] + 0.5, m["z"], m["health"] / m["max_health"])


def draw_boss_model():
    if not boss["alive"]:
        if boss["death_timer"] > 1.2:
            return
        sink = boss["death_timer"] / 1.2
        glPushMatrix()
        glTranslatef(boss["x"], -sink * 3.0, boss["z"])
        glRotatef(boss["angle"], 0, 1, 0)
        draw_sphere(0, 3.0, 0, 1.6, (0.15, 0.05, 0.06))
        glPopMatrix()
        return

    pulse = 0.5 + 0.5 * math.sin(sim_time * (8 if boss["enraged"] else 3))
    aura_col = (0.9, 0.15, 0.1) if boss["enraged"] else (0.5, 0.1, 0.6)
    draw_flat_ring(boss["x"], 0.03, boss["z"], 2.6 + pulse * 0.3, aura_col, 0.25 + 0.15 * pulse)

    col = (1.0, 1.0, 1.0) if boss["hit_flash"] > 0 else (
        0.55 + 0.2 * pulse if boss["enraged"] else 0.35, 0.12, 0.16 if not boss["enraged"] else 0.16)

    telegraph_glow = boss["state"] == "telegraph"
    if telegraph_glow:
        col = (1.0, 0.6, 0.15)

    glPushMatrix()
    glTranslatef(boss["x"], 0, boss["z"])
    glRotatef(boss["angle"], 0, 1, 0)
    draw_cylinder(0, 0, 0, 1.3, 2.6, col, top_radius=1.6)
    draw_sphere(0, 3.1, 0, 1.05, col, 16, 16)
    draw_cone(-0.5, 3.6, 0, 0.18, 0.55, (0.85, 0.8, 0.75))
    draw_cone(0.5, 3.6, 0, 0.18, 0.55, (0.85, 0.8, 0.75))
    eye_col = (1.0, 0.3, 0.05) if boss["enraged"] else (1.0, 0.85, 0.2)
    draw_sphere(-0.3, 3.15, 0.85, 0.14, eye_col)
    draw_sphere(0.3, 3.15, 0.85, 0.14, eye_col)
    draw_cylinder(1.5, 1.6, 0, 0.28, 2.2, (0.4, 0.15, 0.18))
    draw_cylinder(-1.5, 1.6, 0, 0.28, 2.2, (0.4, 0.15, 0.18))
    glPopMatrix()

    draw_health_bar_world(boss["x"], 4.4, boss["z"], boss["health"] / boss["max_health"], width=2.6)


def draw_projectiles_and_particles():
    glDisable(GL_LIGHTING)
    for p in projectiles:
        glColor3f(*p["color"])
        glPushMatrix()
        glTranslatef(p["x"], p["y"], p["z"])
        glutSolidSphere(p["radius"], 8, 8)
        glPopMatrix()
    for p in particles:
        life_frac = max(0.0, p["life"] / 0.7)
        glColor3f(p["color"][0] * life_frac, p["color"][1] * life_frac, p["color"][2] * life_frac)
        glPushMatrix()
        glTranslatef(p["x"], p["y"], p["z"])
        glutSolidSphere(p["size"] * life_frac, 6, 6)
        glPopMatrix()
    glEnable(GL_LIGHTING)


def draw_dust():
    glDisable(GL_LIGHTING)
    glEnable(GL_BLEND)
    glBlendFunc(GL_SRC_ALPHA, GL_ONE)
    glColor4f(0.7, 0.65, 0.5, 0.35)
    glPointSize(2.0)
    glBegin(GL_POINTS)
    for d in dust:
        glVertex3f(d["x"], d["y"], d["z"])
    glEnd()
    glDisable(GL_BLEND)
    glEnable(GL_LIGHTING)


# ==========================================================================
# LIGHTING / FOG / CAMERA
# ==========================================================================
def setup_lighting():
    glEnable(GL_LIGHTING)
    glEnable(GL_LIGHT0)
    glEnable(GL_LIGHT1)
    glEnable(GL_LIGHT2)
    glEnable(GL_LIGHT3)
    glEnable(GL_NORMALIZE)
    glEnable(GL_COLOR_MATERIAL)
    glColorMaterial(GL_FRONT_AND_BACK, GL_AMBIENT_AND_DIFFUSE)

    glLightfv(GL_LIGHT0, GL_POSITION, [0.3, 1.0, 0.2, 0.0])
    glLightfv(GL_LIGHT0, GL_AMBIENT, [0.07, 0.07, 0.10, 1.0])
    glLightfv(GL_LIGHT0, GL_DIFFUSE, [0.16, 0.16, 0.22, 1.0])

    for light in (GL_LIGHT1, GL_LIGHT2, GL_LIGHT3):
        glLightf(light, GL_CONSTANT_ATTENUATION, 1.0)
        glLightf(light, GL_LINEAR_ATTENUATION, 0.06)
        glLightf(light, GL_QUADRATIC_ATTENUATION, 0.05)

    glEnable(GL_DEPTH_TEST)
    glEnable(GL_FOG)
    glFogi(GL_FOG_MODE, GL_EXP2)
    glFogfv(GL_FOG_COLOR, [0.02, 0.015, 0.03, 1.0])
    glFogf(GL_FOG_DENSITY, 0.026)
    glHint(GL_FOG_HINT, GL_NICEST)


def update_lights():
    flick = 0.85 + 0.15 * math.sin(sim_time * 13.0) + 0.05 * math.sin(sim_time * 27.3)
    glLightfv(GL_LIGHT1, GL_POSITION, [player["x"], 2.2, player["z"], 1.0])
    glLightfv(GL_LIGHT1, GL_DIFFUSE, [1.0 * flick, 0.55 * flick, 0.22 * flick, 1.0])

    flick2 = 0.8 + 0.2 * math.sin(sim_time * 9.0 + 1.5)
    glLightfv(GL_LIGHT2, GL_POSITION, [0.0, 6.0, -45.0, 1.0])
    glLightfv(GL_LIGHT2, GL_DIFFUSE, [0.9 * flick2, 0.45 * flick2, 0.15 * flick2, 1.0])

    boss_energy = 1.0
    if boss.get("alive") and boss.get("enraged"):
        boss_energy = 1.3 + 0.3 * math.sin(sim_time * 12.0)
    flick3 = (0.8 + 0.2 * math.sin(sim_time * 6.0 + 3.0)) * boss_energy
    glLightfv(GL_LIGHT3, GL_POSITION, [0.0, 7.0, -75.0, 1.0])
    glLightfv(GL_LIGHT3, GL_DIFFUSE, [0.9 * flick3, 0.15 * flick3, 0.18 * flick3, 1.0])


def setup_camera():
    rad = math.radians(player["angle"])
    fx, fz = math.sin(rad), -math.cos(rad)
    if camera_mode == "third":
        cam_dist, cam_h = 8.5, 4.8
        camx = player["x"] - fx * cam_dist
        camz = player["z"] - fz * cam_dist
        camy = player["y"] + cam_h
        camx, camz = resolve_wall_collisions(camx, camz, 0.4, active_walls())
        lookx, looky, lookz = player["x"] + fx * 2, player["y"] + 1.2, player["z"] + fz * 2
        gluLookAt(camx, camy, camz, lookx, looky, lookz, 0, 1, 0)
    else:
        camx, camy, camz = player["x"] + fx * 0.3, player["y"] + 1.6, player["z"] + fz * 0.3
        gluLookAt(camx, camy, camz, camx + fx * 5, camy, camz + fz * 5, 0, 1, 0)


def setup_menu_camera():
    a = sim_time * 0.12
    cx = math.sin(a) * 42
    cz = -40 + math.cos(a) * 42
    gluLookAt(cx, 22, cz, 0, 1, -45, 0, 1, 0)


# ==========================================================================
# 2D / HUD
# ==========================================================================
def begin_2d():
    glMatrixMode(GL_PROJECTION)
    glPushMatrix()
    glLoadIdentity()
    gluOrtho2D(0, WIN_W, 0, WIN_H)
    glMatrixMode(GL_MODELVIEW)
    glPushMatrix()
    glLoadIdentity()
    glDisable(GL_LIGHTING)
    glDisable(GL_DEPTH_TEST)
    glDisable(GL_FOG)


def end_2d():
    glEnable(GL_DEPTH_TEST)
    glEnable(GL_LIGHTING)
    glEnable(GL_FOG)
    glMatrixMode(GL_PROJECTION)
    glPopMatrix()
    glMatrixMode(GL_MODELVIEW)
    glPopMatrix()


def draw_text(x, y, text, font=GLUT_BITMAP_HELVETICA_18, color=(1, 1, 1)):
    glColor3f(*color)
    glRasterPos2f(x, y)
    for ch in text:
        glutBitmapCharacter(font, ord(ch))


def text_width(text, font=GLUT_BITMAP_HELVETICA_18):
    return sum(glutBitmapWidth(font, ord(c)) for c in text)


def draw_rect2d(x, y, w, h, color, alpha=1.0):
    glEnable(GL_BLEND)
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
    glColor4f(color[0], color[1], color[2], alpha)
    glBegin(GL_QUADS)
    glVertex2f(x, y); glVertex2f(x + w, y)
    glVertex2f(x + w, y + h); glVertex2f(x, y + h)
    glEnd()
    glDisable(GL_BLEND)


def draw_bar(x, y, w, h, frac, bg, fg):
    frac = max(0.0, min(1.0, frac))
    draw_rect2d(x, y, w, h, bg, 0.85)
    draw_rect2d(x, y, w * frac, h, fg, 0.95)
    glColor3f(0.05, 0.05, 0.05)
    glBegin(GL_LINE_LOOP)
    glVertex2f(x, y); glVertex2f(x + w, y); glVertex2f(x + w, y + h); glVertex2f(x, y + h)
    glEnd()


def draw_hud():
    begin_2d()

    draw_bar(24, WIN_H - 44, 260, 22, player["health"] / player["max_health"], (0.25, 0.05, 0.05), (0.8, 0.15, 0.15))
    draw_text(30, WIN_H - 39, "HP  %d / %d" % (max(0, int(player["health"])), int(player["max_health"])), color=(1, 1, 1))

    draw_bar(24, WIN_H - 74, 260, 18, player["mana"] / player["max_mana"], (0.05, 0.08, 0.25), (0.2, 0.4, 0.95))
    draw_text(30, WIN_H - 70, "MP  %d / %d" % (int(player["mana"]), int(player["max_mana"])), font=GLUT_BITMAP_HELVETICA_12, color=(1, 1, 1))

    ability = RANGED_ABILITIES[player["ranged_type"]]
    draw_text(24, WIN_H - 96, "Ability [%d]: %s (cost %d)" % (player["ranged_type"], ability["name"], ability["cost"]),
               font=GLUT_BITMAP_HELVETICA_12, color=(0.8, 0.85, 1.0))

    draw_text(WIN_W - 210, WIN_H - 30, "Keys: %d / %d" % (player["keys"], REQUIRED_KEYS), color=(1.0, 0.85, 0.3))
    draw_text(WIN_W - 210, WIN_H - 54, "Treasure: %d" % player["treasure"], color=(0.9, 0.75, 0.25))
    draw_text(WIN_W - 210, WIN_H - 78, "Score: %d" % player["score"], color=(1, 1, 1))

    if boss["state"] != "dormant" and boss["alive"]:
        draw_bar(WIN_W / 2 - 180, WIN_H - 34, 360, 16, boss["health"] / boss["max_health"], (0.2, 0.03, 0.03), (0.85, 0.15, 0.15))
        draw_text(WIN_W / 2 - 40, WIN_H - 55, "DUNGEON BOSS" + (" - ENRAGED" if boss["enraged"] else ""),
                   font=GLUT_BITMAP_HELVETICA_12, color=(1.0, 0.4, 0.3))

    if message_timer > 0:
        alpha = min(1.0, message_timer)
        w = text_width(message_text, GLUT_BITMAP_HELVETICA_18)
        draw_rect2d(WIN_W / 2 - w / 2 - 14, WIN_H - 130, w + 28, 30, (0, 0, 0), 0.4 * alpha)
        glColor3f(1.0, 0.9, 0.6)
        glRasterPos2f(WIN_W / 2 - w / 2, WIN_H - 122)
        for ch in message_text:
            glutBitmapCharacter(GLUT_BITMAP_HELVETICA_18, ord(ch))

    hint = "WASD move | Mouse look | LClick sword | RClick spell | 1/2 ability | E interact | M map | R checkpoint"
    hw = text_width(hint, GLUT_BITMAP_HELVETICA_12)
    draw_text(WIN_W / 2 - hw / 2, 14, hint, font=GLUT_BITMAP_HELVETICA_12, color=(0.6, 0.6, 0.65))

    if flash_timer > 0:
        draw_rect2d(0, 0, WIN_W, WIN_H, (0.8, 0.0, 0.0), min(0.45, flash_timer))
    if heal_flash_timer > 0:
        draw_rect2d(0, 0, WIN_W, WIN_H, (0.1, 0.9, 0.3), min(0.25, heal_flash_timer))

    if minimap_on:
        draw_minimap()

    end_2d()


def draw_minimap():
    mx, my, mw, mh = WIN_W - 210, WIN_H - 320, 190, 210
    draw_rect2d(mx, my, mw, mh, (0, 0, 0), 0.55)

    all_rects = [ROOM_START, CORR1, ROOM2, BRANCH_CORR, ROOM_TREASURE, GATE_CORR, ROOM_BOSS]
    minx = min(r[0] for r in all_rects) - 3
    maxx = max(r[1] for r in all_rects) + 3
    minz = min(r[2] for r in all_rects) - 3
    maxz = max(r[3] for r in all_rects) + 3
    sx = mw / (maxx - minx)
    sz = mh / (maxz - minz)
    s = min(sx, sz)

    def wpt(x, z):
        return (mx + (x - minx) * s, my + mh - (z - minz) * s)

    for r in all_rects:
        x0, y0 = wpt(r[0], r[2]); x1, y1 = wpt(r[1], r[3])
        draw_rect2d(min(x0, x1), min(y0, y1), abs(x1 - x0), abs(y1 - y0), (0.35, 0.32, 0.4), 0.7)

    for m in monsters:
        if not m["alive"]:
            continue
        px, py = wpt(m["x"], m["z"])
        draw_rect2d(px - 3, py - 3, 6, 6, (0.9, 0.2, 0.2), 0.9)

    if boss["alive"] and boss["state"] != "dormant":
        px, py = wpt(boss["x"], boss["z"])
        draw_rect2d(px - 5, py - 5, 10, 10, (1.0, 0.4, 0.05), 0.95)

    for p in pickups:
        if p["taken"]:
            continue
        px, py = wpt(p["x"], p["z"])
        col = (1.0, 0.85, 0.2) if p["type"] == "key" else ((0.9, 0.75, 0.2) if p["type"] == "chest" else (0.3, 0.8, 0.9))
        draw_rect2d(px - 2, py - 2, 4, 4, col, 0.9)

    px, py = wpt(player["x"], player["z"])
    draw_rect2d(px - 3, py - 3, 6, 6, (0.3, 0.9, 0.3), 1.0)

    draw_text(mx, my + mh + 4, "MINIMAP (M)", font=GLUT_BITMAP_HELVETICA_12, color=(0.8, 0.8, 0.85))


def draw_center_text(text, y_off, font=GLUT_BITMAP_TIMES_ROMAN_24, color=(1, 1, 1)):
    w = text_width(text, font)
    draw_text(WIN_W / 2 - w / 2, WIN_H / 2 + y_off, text, font=font, color=color)


def draw_menu_overlay():
    begin_2d()
    draw_rect2d(0, 0, WIN_W, WIN_H, (0.0, 0.0, 0.0), 0.45)
    draw_center_text("DARK FIGHT", 170, GLUT_BITMAP_TIMES_ROMAN_24, (0.95, 0.75, 0.25))
    draw_center_text("A FANTASY DUNGEON", 140, GLUT_BITMAP_HELVETICA_18, (0.85, 0.85, 0.9))
    draw_center_text("CSE 423 Lab Project  -  3D Dungeon Crawler", 110, GLUT_BITMAP_HELVETICA_12, (0.6, 0.6, 0.65))

    lines = [
        "Explore 4 connected rooms. Fight goblins, orcs and archers.",
        "Collect 2 keys and treasure. Avoid the floor traps.",
        "Unlock the gate, defeat the Dungeon Boss, and escape.",
        "",
        "W/S move   A/D strafe   Mouse look   LClick sword   RClick spell",
        "1/2 switch spell   E interact   M minimap   R checkpoint   ESC quit",
    ]
    y = WIN_H / 2 + 40
    for line in lines:
        w = text_width(line, GLUT_BITMAP_HELVETICA_12)
        draw_text(WIN_W / 2 - w / 2, y, line, font=GLUT_BITMAP_HELVETICA_12, color=(0.85, 0.85, 0.9))
        y -= 22

    pulse = 0.6 + 0.4 * math.sin(sim_time * 3.0)
    draw_center_text("PRESS ENTER TO BEGIN YOUR DESCENT", -110, GLUT_BITMAP_HELVETICA_18, (pulse, pulse * 0.9, 0.3))
    end_2d()


def draw_death_overlay():
    begin_2d()
    draw_rect2d(0, 0, WIN_W, WIN_H, (0.15, 0.0, 0.0), 0.55)
    draw_center_text("YOU DIED", 40, GLUT_BITMAP_TIMES_ROMAN_24, (0.9, 0.15, 0.15))
    draw_center_text("Press R to respawn at your last checkpoint", -10, GLUT_BITMAP_HELVETICA_18, (0.9, 0.85, 0.85))
    end_2d()


def draw_win_overlay():
    begin_2d()
    draw_rect2d(0, 0, WIN_W, WIN_H, (0.0, 0.08, 0.02), 0.55)
    pulse = 0.7 + 0.3 * math.sin(sim_time * 2.0)
    draw_center_text("MISSION COMPLETE", 60, GLUT_BITMAP_TIMES_ROMAN_24, (0.3 * pulse + 0.3, 0.9 * pulse, 0.3))
    draw_center_text("Score: %d   Treasure: %d   Time: %.0fs" % (player["score"], player["treasure"], win_timer),
                       10, GLUT_BITMAP_HELVETICA_18, (0.9, 0.9, 0.85))
    draw_center_text("Press ENTER to play again", -40, GLUT_BITMAP_HELVETICA_18, (0.8, 0.85, 0.8))
    end_2d()


# ==========================================================================
# DISPLAY
# ==========================================================================
def draw_world():
    setup_lighting_state_only()
    update_lights()
    draw_level_static()
    draw_traps()
    draw_pickups()
    for m in monsters:
        draw_monster(m)
    draw_boss_model()
    draw_player_model()
    draw_projectiles_and_particles()
    draw_dust()


def setup_lighting_state_only():
    # lighting/fog toggles are set once in init(); nothing per-frame needed here
    # besides update_lights(), kept as a separate hook for clarity/extension.
    pass


def display():
    glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
    glMatrixMode(GL_MODELVIEW)
    glLoadIdentity()

    if game_state == "menu":
        setup_menu_camera()
        draw_world()
        draw_menu_overlay()
    else:
        setup_camera()
        draw_world()
        draw_hud()
        if game_state == "dead":
            draw_death_overlay()
        elif game_state == "won":
            draw_win_overlay()

    glutSwapBuffers()


def reshape(w, h):
    global WIN_W, WIN_H
    if h == 0:
        h = 1
    WIN_W, WIN_H = w, h
    glViewport(0, 0, w, h)
    glMatrixMode(GL_PROJECTION)
    glLoadIdentity()
    gluPerspective(62.0, float(w) / float(h), 0.1, 220.0)
    glMatrixMode(GL_MODELVIEW)
    glLoadIdentity()


# ==========================================================================
# INPUT
# ==========================================================================
def start_game():
    global game_state
    init_level()
    game_state = "playing"
    try:
        glutSetCursor(GLUT_CURSOR_NONE)
        glutWarpPointer(WIN_W // 2, WIN_H // 2)
    except Exception:
        pass
    show_message("Find the keys. Beware the dark.", 3.0)


def keyboard_down(key, x, y):
    global camera_mode, minimap_on

    try:
        k = key.decode("utf-8")
    except Exception:
        k = ""

    if key == b"\x1b":  # ESC
        try:
            glutLeaveMainLoop()
        except Exception:
            sys.exit(0)
        return

    if k in ("\r", "\n"):
        if game_state in ("menu", "won"):
            start_game()
        return

    keys_pressed.add(key.lower() if isinstance(key, bytes) else key)

    kl = k.lower()
    if kl == "m":
        minimap_on = not minimap_on
    elif kl == "r":
        player_checkpoint()
    elif kl == "e":
        player_interact()
    elif kl == "1":
        player["ranged_type"] = 1
    elif kl == "2":
        player["ranged_type"] = 2
    elif kl == "v":
        camera_mode = "first" if camera_mode == "third" else "third"


def keyboard_up(key, x, y):
    k = key.lower() if isinstance(key, bytes) else key
    if k in keys_pressed:
        keys_pressed.remove(k)


def mouse_click(button, state, x, y):
    if game_state != "playing":
        return
    if state != GLUT_DOWN:
        return
    if button == GLUT_LEFT_BUTTON:
        player_sword_attack()
    elif button == GLUT_RIGHT_BUTTON:
        player_ranged_attack()


def passive_motion(x, y):
    if game_state != "playing":
        return
    dx = x - WIN_W // 2
    dy = y - WIN_H // 2
    if dx != 0:
        player["angle"] = (player["angle"] + dx * 0.15) % 360.0
    if dx != 0 or dy != 0:
        try:
            glutWarpPointer(WIN_W // 2, WIN_H // 2)
        except Exception:
            pass


# ==========================================================================
# MAIN LOOP TIMER
# ==========================================================================
FRAME_MS = 16


def timer_tick(value):
    update_world(FRAME_MS / 1000.0)
    glutPostRedisplay()
    glutTimerFunc(FRAME_MS, timer_tick, 0)


# ==========================================================================
# INIT / ENTRY POINT
# ==========================================================================
def init_gl():
    global quad
    glClearColor(0.02, 0.015, 0.03, 1.0)
    glEnable(GL_DEPTH_TEST)
    glShadeModel(GL_SMOOTH)
    quad = gluNewQuadric()
    gluQuadricNormals(quad, GLU_SMOOTH)
    setup_lighting()


def main():
    glutInit(sys.argv)
    glutInitDisplayMode(GLUT_DOUBLE | GLUT_RGB | GLUT_DEPTH)
    glutInitWindowSize(WIN_W, WIN_H)
    glutCreateWindow(b"Dark Fight - A Fantasy Dungeon")

    init_gl()
    init_level()  # so menu backdrop has valid data to render

    glutDisplayFunc(display)
    glutReshapeFunc(reshape)
    glutKeyboardFunc(keyboard_down)
    glutKeyboardUpFunc(keyboard_up)
    glutMouseFunc(mouse_click)
    glutPassiveMotionFunc(passive_motion)
    glutTimerFunc(FRAME_MS, timer_tick, 0)

    glutMainLoop()


if __name__ == "__main__":
    main()
