import pyglet
pyglet.options['debug_gl'] = False

from game import Game

window = pyglet.window.Window(1024, 768, 'Dungeon')

game = Game(window)
game.start()

pyglet.app.run()
