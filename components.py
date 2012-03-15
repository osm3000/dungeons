import random

import game
import level_object
import player
from position import Position
import shadowcaster
from render import Renderable
from temp import corpse_texes


class Blocker(level_object.Component):

    component_name = 'blocker'

    def __init__(self, blocks_sight=False, blocks_movement=False, bump_function=None):
        self.blocks_sight = blocks_sight
        self.blocks_movement = blocks_movement
        if bump_function:
            self.bump = bump_function

    @staticmethod
    def bump(blocker, who):
        if who.has_component(player.Player):
            who.level.game.message('You bump into %s' % blocker.owner.name)


class FOV(level_object.Component):

    component_name = 'fov'

    def __init__(self, radius, updated_callback=None):
        self.radius = radius
        self.lightmap = {}
        self.updated_callback = updated_callback

    def update_light(self):
        old_lightmap = self.lightmap.copy()
        pos = self.owner.position
        self.lightmap.clear()
        self.lightmap[pos.x, pos.y] = 1
        caster = shadowcaster.ShadowCaster(self.owner.level.blocks_sight, self.set_light)
        caster.calculate_light(pos.x, pos.y, self.radius)
        if self.updated_callback:
            self.updated_callback(old_lightmap, self.lightmap)

    def set_light(self, x, y, intensity):
        self.lightmap[x, y] = intensity

    def is_in_fov(self, x, y):
        return self.lightmap.get((x, y), 0) > 0


class Movement(level_object.Component):

    component_name = 'movement'

    def move(self, dx, dy):
        new_x = self.owner.position.x + dx
        new_y = self.owner.position.y + dy

        blocker = self.owner.level.blocks_movement(new_x, new_y)
        if isinstance(blocker, level_object.LevelObject):
            blocker.blocker.bump(blocker.blocker, self.owner)
        elif not blocker:
            self.owner.level.move_object(self.owner, new_x, new_y)

            # TODO: use some kind of events/signals
            if self.owner.has_component(FOV):
                self.owner.fov.update_light()


class Fighter(level_object.Component):

    component_name = 'fighter'

    def __init__(self, max_health, attack, defense):
        self.health = self.max_health = max_health
        self.attack = attack
        self.defense = defense

    def do_attack(self, target):
        dmg = max(0, self.attack - target.fighter.defense)
        target.fighter.take_damage(dmg, self.owner)

    def take_damage(self, damage, source):
        self.health -= damage

        if source.has_component(player.Player):
            source.level.game.message('You hit %s for %d hp' % (self.owner.name, damage))
        elif self.owner.has_component(player.Player):
            self.owner.level.game.message('%s hits you for %d hp' % (source.name, damage))

        self.owner.level.game.animate_damage(self.owner.position.x, self.owner.position.y, damage)

        if self.health <= 0:
            self.die()

    def die(self):
        if self.owner.has_component(player.Player):
            self.owner.level.game.message('You die')
            raise game.GameExit()
        else:
            self.owner.level.game.message('%s dies' % self.owner.name)
            self.owner.level.add_object(level_object.LevelObject(
                Renderable(random.choice(corpse_texes)),
                level_object.Description('%s\'s corpse' % self.owner.name),
                Position(self.owner.position.x, self.owner.position.y, Position.ORDER_FLOOR + 1),
            ))
            self.owner.level.remove_object(self.owner)
