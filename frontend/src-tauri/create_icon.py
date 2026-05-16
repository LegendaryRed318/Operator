from PIL import Image, ImageDraw
import os

os.makedirs('icons', exist_ok=True)
img = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.ellipse((8, 8, 56, 56), fill=(0, 122, 204, 255))
d.text((18, 18), 'O', fill=(255, 255, 255, 255))
img.save('icons/icon.ico', format='ICO', sizes=[(64, 64), (32, 32), (16, 16)])
print('wrote icons/icon.ico', os.path.getsize('icons/icon.ico'))
