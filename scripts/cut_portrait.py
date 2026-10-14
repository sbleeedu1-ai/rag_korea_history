"""인물 초상의 단색 배경을 지워 _cut 판을 만든다(10-12, 수양대군 초상에 처음 씀).

실행: python scripts/cut_portrait.py 원본.png 결과_cut.png 확인용.png
위 가장자리와, 양옆은 인물이 닿기 전 줄까지만 씨앗으로 두고 거기에 이어진 배경색만 지운다
(어두운 망토가 가장자리에 닿아도 구멍이 나지 않게). 확인용 그림은 빨간 바탕에 올린 반 크기 미리보기.
"""
import sys
from collections import deque
from PIL import Image, ImageFilter
src_path, out_path, check_path = sys.argv[1:4]
src = Image.open(src_path).convert('RGB'); w, h = src.size; px = src.load()
samples = [px[x, 3] for x in range(0, w, 20)]
bg = tuple(sum(c[i] for c in samples) / len(samples) for i in range(3))
near = lambda c, t=20: sum((c[i] - bg[i]) ** 2 for i in range(3)) <= t * t
seeds = [(x, 0) for x in range(w) if near(px[x, 0])]
for x0 in (0, w - 1):
    for y in range(h):
        if not near(px[x0, y]): break   # 인물이 가장자리에 닿는 줄부터는 씨앗으로 쓰지 않음
        seeds.append((x0, y))
mask = bytearray(w * h); q = deque(seeds)
while q:
    x, y = q.popleft(); i = y * w + x
    if mask[i] or not near(px[x, y]): continue
    mask[i] = 1
    for nx, ny in ((x+1, y), (x-1, y), (x, y+1), (x, y-1)):
        if 0 <= nx < w and 0 <= ny < h and not mask[ny * w + nx]: q.append((nx, ny))
alpha = Image.frombytes('L', (w, h), bytes(0 if m else 255 for m in mask))
alpha = alpha.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(0.8))
cut = src.convert('RGBA'); cut.putalpha(alpha); cut.save(out_path)
chk = Image.new('RGBA', (w, h), (180, 40, 40, 255)); chk.alpha_composite(cut)
chk.convert('RGB').resize((w // 2, h // 2)).save(check_path)
print('지운 비율 %', round(sum(mask) / len(mask) * 100, 1))
