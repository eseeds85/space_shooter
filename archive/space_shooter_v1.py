"""
2D Space Shooter — single-file Pygame script

Controls
- Move: Arrow Keys or WASD
- Shoot: Space (hold for auto-fire)
- Dash: Left Shift (short burst, brief invulnerability)
- Pause: P
- Quit: Esc

Requirements
- Python 3.9+
- pygame (pip install pygame)

Run
python space_shooter.py

Notes
- Pure code, no image/audio assets needed (shapes + generated effects)
- Window is resizable; uses delta time for smooth motion
"""

import math
import random
import sys
from dataclasses import dataclass

import pygame as pg

# ---------------------------
# Configuration
# ---------------------------
WIDTH, HEIGHT = 900, 600
FPS = 60
BG_COLOR = (6, 8, 18)
STAR_COLOR = (180, 200, 255)
UI_COLOR = (235, 240, 250)

PLAYER_COLOR = (90, 220, 255)
BULLET_COLOR = (255, 240, 120)
ENEMY_COLOR = (255, 80, 120)
ELITE_COLOR = (255, 140, 60)
POWERUP_COLOR = (140, 255, 160)
PARTICLE_COLOR = (255, 200, 120)

MAX_STARS = 140

# Gameplay tuning
PLAYER_SPEED = 360
PLAYER_ACCEL = 1800
PLAYER_FRICTION = 0.85
PLAYER_RADIUS = 14
PLAYER_FIRE_COOLDOWN = 0.14
PLAYER_DASH_COOLDOWN = 1.6
PLAYER_DASH_TIME = 0.18
PLAYER_DASH_MULT = 3.6
PLAYER_MAX_HP = 4

BULLET_SPEED = 700
BULLET_RADIUS = 3
BULLET_SPREAD = 0.06  # radians at edges while holding
BULLET_LIFE = 1.4

ENEMY_MIN_SPAWN = 0.45
ENEMY_MAX_SPAWN = 0.9
ENEMY_BASE_SPEED = 90
ENEMY_SPEED_VARIANCE = 90
ENEMY_RADIUS = 16
ELITE_RADIUS = 22
ELITE_HP = 3
WAVE_TIME = 35  # seconds until difficulty scales up

POWERUP_CHANCE = 0.12
POWERUP_DURATION = 12

# ---------------------------
# Utility
# ---------------------------
vec2 = pg.math.Vector2


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def circle_collide(p1, r1, p2, r2):
    return p1.distance_to(p2) <= (r1 + r2)


# ---------------------------
# Entities
# ---------------------------
@dataclass
class Bullet:
    pos: vec2
    vel: vec2
    life: float = BULLET_LIFE
    radius: int = BULLET_RADIUS

    def update(self, dt):
        self.pos += self.vel * dt
        self.life -= dt

    def draw(self, s):
        pg.draw.circle(s, BULLET_COLOR, self.pos, self.radius)


@dataclass
class Particle:
    pos: vec2
    vel: vec2
    life: float
    radius: float

    def update(self, dt):
        self.pos += self.vel * dt
        self.life -= dt
        self.radius = max(0, self.radius - 40 * dt)
        self.vel *= 0.98

    def draw(self, s):
        if self.life > 0:
            alpha = clamp(int(255 * (self.life / 0.9)), 0, 255)
            surf = pg.Surface((self.radius * 2 + 2, self.radius * 2 + 2), pg.SRCALPHA)
            pg.draw.circle(surf, (*PARTICLE_COLOR, alpha), (surf.get_width() // 2, surf.get_height() // 2), int(self.radius))
            s.blit(surf, (self.pos.x - surf.get_width() // 2, self.pos.y - surf.get_height() // 2))


class Enemy:
    def __init__(self, pos: vec2, speed: float, elite=False):
        self.pos = vec2(pos)
        self.speed = speed
        self.radius = ELITE_RADIUS if elite else ENEMY_RADIUS
        self.elite = elite
        self.hp = ELITE_HP if elite else 1
        self.wobble_t = random.random() * 10

    def update(self, dt, player_pos: vec2):
        # simple seek with sine wobble
        to_player = (player_pos - self.pos)
        dist = to_player.length() + 1e-5
        dir = to_player / dist
        self.wobble_t += dt * (1.3 if self.elite else 1.0)
        wobble = vec2(math.cos(self.wobble_t), math.sin(self.wobble_t)) * (60 if self.elite else 40)
        self.pos += (dir * self.speed + wobble) * dt

    def draw(self, s):
        color = ELITE_COLOR if self.elite else ENEMY_COLOR
        pg.draw.circle(s, color, self.pos, self.radius)
        if self.elite:
            # small inner core
            pg.draw.circle(s, (255, 220, 200), self.pos, max(2, self.radius // 3))


class PowerUp:
    TYPES = ("rapid", "shield", "spread")

    def __init__(self, pos: vec2):
        self.pos = vec2(pos)
        self.radius = 12
        self.kind = random.choice(PowerUp.TYPES)
        self.t = 0

    def update(self, dt):
        self.t += dt
        self.pos.y += math.sin(self.t * 2) * 20 * dt

    def draw(self, s):
        # draw a diamond with an icon letter
        pg.draw.polygon(s, POWERUP_COLOR, [self.pos + vec2(0, -self.radius), self.pos + vec2(self.radius, 0), self.pos + vec2(0, self.radius), self.pos + vec2(-self.radius, 0)])
        label = {"rapid": "R", "shield": "S", "spread": "/"}[self.kind]
        txt = pg.font.SysFont(None, 18).render(label, True, (20, 40, 30))
        s.blit(txt, txt.get_rect(center=self.pos))


class Player:
    def __init__(self, pos: vec2):
        self.pos = vec2(pos)
        self.vel = vec2(0, 0)
        self.radius = PLAYER_RADIUS
        self.hp = PLAYER_MAX_HP
        self.invuln = 1.2  # start safe
        self.fire_cd = 0.0
        self.dash_cd = 0.0
        self.dash_t = 0.0
        self.score = 0
        self.mult = 1
        self.mult_t = 0.0
        self.power = {"rapid": 0.0, "shield": 0.0, "spread": 0.0}

    def alive(self):
        return self.hp > 0

    def apply_powerup(self, kind):
        self.power[kind] = POWERUP_DURATION
        if kind == "shield":
            self.invuln = max(self.invuln, 0.75)  # instant brief invuln on pickup

    def update(self, dt, keys, bounds):
        # handle powers decay
        for k in self.power:
            self.power[k] = max(0.0, self.power[k] - dt)
        self.mult_t = max(0.0, self.mult_t - dt)
        if self.mult_t <= 0:
            self.mult = 1

        acc = vec2(0, 0)
        if keys[pg.K_LEFT] or keys[pg.K_a]:
            acc.x -= PLAYER_ACCEL
        if keys[pg.K_RIGHT] or keys[pg.K_d]:
            acc.x += PLAYER_ACCEL
        if keys[pg.K_UP] or keys[pg.K_w]:
            acc.y -= PLAYER_ACCEL
        if keys[pg.K_DOWN] or keys[pg.K_s]:
            acc.y += PLAYER_ACCEL

        self.vel += acc * dt
        self.vel *= PLAYER_FRICTION

        # dash
        self.dash_cd -= dt
        if (keys[pg.K_LSHIFT] or keys[pg.K_RSHIFT]) and self.dash_cd <= 0 and self.dash_t <= 0:
            if self.vel.length_squared() > 1:
                self.dash_t = PLAYER_DASH_TIME
                self.dash_cd = PLAYER_DASH_COOLDOWN
                self.invuln = max(self.invuln, PLAYER_DASH_TIME + 0.05)

        if self.dash_t > 0:
            self.dash_t -= dt
            self.pos += self.vel * (PLAYER_DASH_MULT * dt)
        else:
            self.pos += self.vel * dt

        self.invuln = max(0.0, self.invuln - dt)

        # clamp to bounds
        w, h = bounds
        self.pos.x = clamp(self.pos.x, self.radius, w - self.radius)
        self.pos.y = clamp(self.pos.y, self.radius, h - self.radius)

        self.fire_cd = max(0.0, self.fire_cd - dt)

    def try_fire(self, bullets, holding=False):
        rate = PLAYER_FIRE_COOLDOWN
        if self.power["rapid"] > 0:
            rate *= 0.55
        if self.fire_cd > 0:
            return
        self.fire_cd = rate

        # spread if powered
        spread = 0
        if self.power["spread"] > 0:
            spread = BULLET_SPREAD

        # small random spread when holding to feel juicy
        jitter = BULLET_SPREAD * 0.6 if holding else 0

        for i in (-1, 0, 1):
            if spread == 0 and i != 0:
                continue
            ang = -math.pi / 2 + i * spread + random.uniform(-jitter, jitter)
            vel = vec2(math.cos(ang), math.sin(ang)) * BULLET_SPEED
            bullets.append(Bullet(self.pos + vec2(0, -self.radius - 2), vel))

    def damage(self, amt):
        if self.invuln > 0 or self.power["shield"] > 0:
            return False
        self.hp -= amt
        self.invuln = 1.0
        return True

    def add_score(self, s):
        self.score += s * self.mult
        self.mult = min(8, self.mult + 1)
        self.mult_t = 4.0

    def draw(self, surf):
        # Triangle ship
        angle = math.atan2(self.vel.y, self.vel.x) if self.vel.length_squared() > 10 else -math.pi / 2
        tip = self.pos + vec2(math.cos(angle), math.sin(angle)) * (self.radius + 4)
        left = self.pos + vec2(math.cos(angle + 2.4), math.sin(angle + 2.4)) * self.radius
        right = self.pos + vec2(math.cos(angle - 2.4), math.sin(angle - 2.4)) * self.radius
        color = PLAYER_COLOR
        if self.invuln > 0 and int(self.invuln * 20) % 2 == 0:
            color = (200, 200, 220)
        pg.draw.polygon(surf, color, [tip, right, left])
        # thruster
        flame_len = 10 + min(20, self.vel.length() * 0.05) * (1.6 if self.dash_t > 0 else 1.0)
        back = (right + left) / 2
        flame = back + vec2(math.cos(angle + math.pi), math.sin(angle + math.pi)) * flame_len
        pg.draw.line(surf, (255, 180, 140), back, flame, 3)


# ---------------------------
# Game
# ---------------------------
class Game:
    def __init__(self):
        pg.init()
        pg.display.set_caption("2D Space Shooter — Pygame")
        self.screen = pg.display.set_mode((WIDTH, HEIGHT), pg.RESIZABLE)
        self.clock = pg.time.Clock()
        self.font = pg.font.SysFont("consolas", 22)
        self.bigfont = pg.font.SysFont("consolas", 46, bold=True)
        self.running = True
        self.reset()

    def reset(self):
        w, h = self.screen.get_size()
        self.player = Player(vec2(w / 2, h * 0.75))
        self.bullets: list[Bullet] = []
        self.enemies: list[Enemy] = []
        self.particles: list[Particle] = []
        self.powerups: list[PowerUp] = []
        self.paused = False
        self.elapsed = 0.0
        self.spawn_t = random.uniform(ENEMY_MIN_SPAWN, ENEMY_MAX_SPAWN)
        self.difficulty = 1.0
        self.starfield = self._make_stars(w, h)

    def _make_stars(self, w, h):
        stars = []
        for _ in range(MAX_STARS):
            x = random.uniform(0, w)
            y = random.uniform(0, h)
            speed = random.uniform(20, 120)
            size = random.randint(1, 3)
            stars.append([x, y, speed, size])
        return stars

    def spawn_enemy(self):
        w, h = self.screen.get_size()
        x = random.uniform(40, w - 40)
        y = -30
        elite = random.random() < clamp(0.05 * self.difficulty, 0, 0.4)
        speed = ENEMY_BASE_SPEED + random.uniform(-ENEMY_SPEED_VARIANCE, ENEMY_SPEED_VARIANCE)
        speed *= (0.8 + 0.25 * self.difficulty)
        self.enemies.append(Enemy(vec2(x, y), speed, elite=elite))

    def add_explosion(self, pos, amount=18, power=1.0):
        for _ in range(amount):
            ang = random.uniform(0, math.tau)
            spd = random.uniform(80, 260) * power
            vel = vec2(math.cos(ang), math.sin(ang)) * spd
            life = random.uniform(0.4, 0.9)
            radius = random.uniform(2, 5)
            self.particles.append(Particle(vec2(pos), vel, life, radius))

    def update(self, dt):
        if self.paused:
            return
        self.elapsed += dt
        # difficulty scales over time
        self.difficulty = 1.0 + (self.elapsed // WAVE_TIME)

        keys = pg.key.get_pressed()
        self.player.update(dt, keys, self.screen.get_size())

        # stars
        w, h = self.screen.get_size()
        for s in self.starfield:
            s[1] += s[2] * dt
            if s[1] > h:
                s[0] = random.uniform(0, w)
                s[1] = -5
                s[2] = random.uniform(20, 120)

        # spawn enemies
        self.spawn_t -= dt
        spmin = max(0.18, ENEMY_MIN_SPAWN / self.difficulty)
        spmax = max(spmin + 0.05, ENEMY_MAX_SPAWN / self.difficulty)
        if self.spawn_t <= 0:
            self.spawn_enemy()
            self.spawn_t = random.uniform(spmin, spmax)

        # fire bullets
        if (keys[pg.K_SPACE]) and self.player.alive():
            self.player.try_fire(self.bullets, holding=True)

        # update bullets
        for b in self.bullets:
            b.update(dt)
        self.bullets = [b for b in self.bullets if 0 <= b.pos.x <= w and -30 <= b.pos.y <= h + 30 and b.life > 0]

        # update enemies
        for e in self.enemies:
            e.update(dt, self.player.pos)
        self.enemies = [e for e in self.enemies if -60 <= e.pos.y <= h + 120]

        # collisions: bullets -> enemies
        for e in list(self.enemies):
            hit = False
            for b in list(self.bullets):
                if circle_collide(e.pos, e.radius, b.pos, b.radius):
                    self.bullets.remove(b)
                    e.hp -= 1
                    hit = True
                    self.add_explosion(b.pos, amount=6, power=0.5)
                    if e.hp <= 0:
                        self.enemies.remove(e)
                        self.player.add_score(15 if e.elite else 7)
                        self.add_explosion(e.pos, amount=24 if e.elite else 16, power=1.4 if e.elite else 1.0)
                        if random.random() < POWERUP_CHANCE * (1.2 if e.elite else 1.0):
                            self.powerups.append(PowerUp(e.pos))
                        break
            if hit:
                continue

        # enemies -> player
        if self.player.alive():
            for e in list(self.enemies):
                if circle_collide(e.pos, e.radius, self.player.pos, self.player.radius):
                    if self.player.damage(1):
                        self.add_explosion(self.player.pos, amount=20, power=1.2)
                    self.enemies.remove(e)
                    self.add_explosion(e.pos, amount=12, power=0.9)

        # powerups
        for p in self.powerups:
            p.update(dt)
        if self.player.alive():
            for p in list(self.powerups):
                if circle_collide(p.pos, p.radius, self.player.pos, self.player.radius + 4):
                    self.player.apply_powerup(p.kind)
                    self.powerups.remove(p)
                    self.add_explosion(p.pos, amount=10, power=0.7)

        # particles
        for pr in self.particles:
            pr.update(dt)
        self.particles = [pr for pr in self.particles if pr.life > 0 and -40 <= pr.pos.x <= w + 40 and -40 <= pr.pos.y <= h + 40]

    def draw(self):
        self.screen.fill(BG_COLOR)
        # stars
        for x, y, _, size in self.starfield:
            pg.draw.circle(self.screen, STAR_COLOR, (int(x), int(y)), size)

        # entities
        for p in self.particles:
            p.draw(self.screen)
        for pu in self.powerups:
            pu.draw(self.screen)
        for e in self.enemies:
            e.draw(self.screen)
        for b in self.bullets:
            b.draw(self.screen)
        self.player.draw(self.screen)

        # UI
        self._draw_ui()

        if not self.player.alive():
            self._draw_game_over()

        if self.paused:
            self._draw_paused()

        pg.display.flip()

    def _draw_ui(self):
        w, _ = self.screen.get_size()
        # HP hearts
        for i in range(PLAYER_MAX_HP):
            cx = 20 + i * 26
            cy = 20
            color = (240, 70, 90) if i < self.player.hp else (80, 60, 70)
            pg.draw.circle(self.screen, color, (cx, cy), 8)
            pg.draw.circle(self.screen, color, (cx + 10, cy), 8)
            pg.draw.polygon(self.screen, color, [(cx - 6, cy + 2), (cx + 16, cy + 2), (cx + 5, cy + 18)])

        # score + multiplier
        score_text = self.font.render(f"Score: {self.player.score}", True, UI_COLOR)
        mult_text = self.font.render(f"x{self.player.mult}", True, UI_COLOR)
        self.screen.blit(score_text, (20, 44))
        self.screen.blit(mult_text, (20, 70))

        # power timers
        px = w - 180
        for name in ("rapid", "shield", "spread"):
            t = self.player.power[name]
            label = name.capitalize()
            pg.draw.rect(self.screen, (60, 70, 90), (px, 16, 150, 16), border_radius=8)
            if t > 0:
                frac = clamp(t / POWERUP_DURATION, 0, 1)
                pg.draw.rect(self.screen, POWERUP_COLOR, (px, 16, int(150 * frac), 16), border_radius=8)
            txt = self.font.render(label, True, UI_COLOR)
            self.screen.blit(txt, (px, 36))
            px += 0
            px = w - 180
            # stack vertically
            for dy, n2 in ((0, "rapid"), (28, "shield"), (56, "spread")):
                pass
        # Re-draw properly stacked bars
        px = w - 180
        for idx, name in enumerate(("rapid", "shield", "spread")):
            y = 16 + idx * 28
            t = self.player.power[name]
            pg.draw.rect(self.screen, (60, 70, 90), (px, y, 150, 16), border_radius=8)
            if t > 0:
                frac = clamp(t / POWERUP_DURATION, 0, 1)
                pg.draw.rect(self.screen, POWERUP_COLOR, (px, y, int(150 * frac), 16), border_radius=8)
            txt = self.font.render(name.capitalize(), True, UI_COLOR)
            self.screen.blit(txt, (px, y + 18))

    def _draw_game_over(self):
        w, h = self.screen.get_size()
        overlay = pg.Surface((w, h), pg.SRCALPHA)
        overlay.fill((10, 10, 20, 170))
        self.screen.blit(overlay, (0, 0))
        title = self.bigfont.render("GAME OVER", True, (255, 210, 210))
        self.screen.blit(title, title.get_rect(center=(w // 2, h // 2 - 40)))
        msg = self.font.render("Press Enter to restart or Esc to quit", True, UI_COLOR)
        self.screen.blit(msg, msg.get_rect(center=(w // 2, h // 2 + 10)))

    def _draw_paused(self):
        w, h = self.screen.get_size()
        overlay = pg.Surface((w, h), pg.SRCALPHA)
        overlay.fill((10, 10, 20, 140))
        self.screen.blit(overlay, (0, 0))
        title = self.bigfont.render("PAUSED", True, (210, 230, 255))
        self.screen.blit(title, title.get_rect(center=(w // 2, h // 2)))

    def handle_events(self):
        for e in pg.event.get():
            if e.type == pg.QUIT:
                self.running = False
            elif e.type == pg.VIDEORESIZE:
                # rebuild starfield scaled to new size
                self.starfield = self._make_stars(e.w, e.h)
            elif e.type == pg.KEYDOWN:
                if e.key == pg.K_ESCAPE:
                    self.running = False
                elif e.key == pg.K_p:
                    if self.player.alive():
                        self.paused = not self.paused
                elif e.key == pg.K_RETURN and not self.player.alive():
                    self.reset()
                elif e.key == pg.K_SPACE and self.player.alive():
                    # manual tap shooting (tap has tighter spread)
                    self.player.try_fire(self.bullets, holding=False)

    def run(self):
        while self.running:
            dt = self.clock.tick(FPS) / 1000.0
            self.handle_events()
            self.update(dt)
            self.draw()
        pg.quit()
        sys.exit()


if __name__ == "__main__":
    Game().run()
