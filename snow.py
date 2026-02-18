import math
import random
import pygame

# =========================
# 設定
# =========================
WIDTH, HEIGHT = 900, 600
FPS = 240
N_PARTICLES = 300

# -------------------------
# “滑らかな揺れ”のための簡易ノイズ
#   - Perlinほど本格ではないが、雪の揺れには十分
#   - 「時間 t を入れると、滑らかに変化する値」を返す
# -------------------------
def smoothstep(x: float) -> float:
    # 0..1 を滑らかに補間する定番関数
    return x * x * (3 - 2 * x)

def hash01(i: int, seed: int) -> float:
    # i と seed から 0..1 の疑似乱数を作る（安定して再現される）
    n = (i * 374761393 + seed * 668265263) & 0xFFFFFFFF
    n = (n ^ (n >> 13)) * 1274126177 & 0xFFFFFFFF
    n = n ^ (n >> 16)
    return (n & 0xFFFFFFFF) / 0xFFFFFFFF

def value_noise_1d(t: float, seed: int) -> float:
    # t の前後整数点の乱数を取り、smoothstepで補間して滑らかにする
    i0 = math.floor(t)
    i1 = i0 + 1
    f = t - i0  # 0..1
    a = hash01(i0, seed)
    b = hash01(i1, seed)
    u = smoothstep(f)
    return a * (1 - u) + b * u  # 0..1

# =========================
# 粒（雪）クラス
# =========================
class SnowParticle:
    def __init__(self):
        self.reset(random.uniform(0, WIDTH), random.uniform(0, HEIGHT))

    def reset(self, x: float, y: float):
        self.x = x
        self.y = y

        # 奥行き：0(奥) .. 1(手前)
        self.depth = random.random()

        self.size = 1 + self.depth * 2.5
        self.alpha = int(70 + self.depth * 185)

        # 基本の重力（落下）を粒ごとに
        self.gravity = 30 + self.depth * 80  # 下向き加速度（px/s^2）

        # 速度（px/s）
        self.vx = 0.0
        self.vy = 20 + self.depth * 150  # 初速は下向き

        # “揺れ”は加速度として少し入れる（ガタガタしない）
        self.sway_amp = 40 + self.depth * 70
        self.sway_speed = 0.25 + random.random() * 0.8

        # 空気抵抗（速度の減衰）：手前ほど少し弱く（重めに見せる）
        self.drag = 1.6 - self.depth * 0.6  # 例: 奥=1.6, 手前=1.0

        self.seed = random.randint(0, 10_000)

    def update(self, dt: float, t: float):
        # --- 風場から加速度を受ける（奥行きで向きが逆） ---
        ax_wind, ay_wind = wind_field(t, self.y, self.depth, self.seed)

        # --- 雪の“ふわふわ”揺れ：滑らかなノイズを横加速度へ ---
        n = value_noise_1d(t * self.sway_speed, self.seed)  # 0..1
        sway = (n * 2 - 1) * self.sway_amp                  # -amp..+amp
        ax_sway = sway  # 加速度として扱う（見た目優先）

        # --- 合成加速度 ---
        ax = ax_wind + ax_sway
        ay = self.gravity + ay_wind  # 重力(+) + 上向きリフト(-)

        # --- 速度更新 ---
        self.vx += ax * dt
        self.vy += ay * dt

        # --- 空気抵抗（指数減衰っぽく） ---
        # dtに比例して速度を縮める → 安定する
        damp = max(0.0, 1.0 - self.drag * dt)
        self.vx *= damp
        self.vy *= damp

        # --- 位置更新 ---
        self.x += self.vx * dt
        self.y += self.vy * dt

        # --- 画面外の再利用 ---
        # 下に抜けたら上へ
        if self.y > HEIGHT + 20:
            self.reset(random.uniform(0, WIDTH), -20)

        # 上に舞い上がって上へ抜けた粒も戻す（強風のとき起きる）
        if self.y < -60:
            self.reset(random.uniform(0, WIDTH), HEIGHT + 20)

        # 横ループ
        if self.x < -50:
            self.x = WIDTH + 50
        elif self.x > WIDTH + 50:
            self.x = -50

    def draw(self, surf: pygame.Surface):
        r = int(self.size)
        s = pygame.Surface((r * 2 + 2, r * 2 + 2), pygame.SRCALPHA)
        pygame.draw.circle(s, (255, 255, 255, self.alpha), (r + 1, r + 1), r)
        surf.blit(s, (self.x - r, self.y - r))


def wind_field(t: float, y: float, depth: float, seed: int) -> tuple[float, float]:
    """
    風場（wind field）を返す。
    戻り値: (ax, ay)
      ax: 横方向の加速度（+右 / -左）
      ay: 縦方向の加速度（+下 / -上） ※上に舞う=ayが負になる
    """

    # 1) 奥行きで風向きを反転：手前=左、奥=右
    # depth: 0(奥) .. 1(手前)
    dir_x = (0.5 - depth)  # 奥:+, 手前:-

    # 2) 高さで風を変える（上の方ほど風が強い、など）
    height_factor = 0.4 + 0.6 * (1.0 - y / HEIGHT)  # 上ほど1に近い

    # 3) 時間でゆっくり変わるベース風 + 小さなノイズ
    base = math.sin(t * 0.35)  # -1..1
    jitter = (value_noise_1d(t * 0.9, seed) * 2 - 1) * 0.35  # -0.35..0.35
    wind_strength = (base + jitter) * 200 * height_factor  # 加速度スケール

    ax = dir_x * wind_strength

    # 4) 舞い上がり（上向きの風）：
    #    「突風っぽい波」×「粒ごとの個体差」×「高さ依存」
    gust = max(0.0, math.sin(t * 1.2 + seed * 0.01))  # 0..1 たまに強くなる
    lift_personal = value_noise_1d(t * 1.1, seed + 999)  # 0..1 粒ごとの癖
    lift = gust * lift_personal * 220 * (0.3 + 0.7 * height_factor)  # 上向き成分

    ay = -lift  # 上向きはマイナス（座標系は下が+）

    return ax, ay


# =========================
# メイン
# =========================
def main():
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("Snow Particles (irregular motion)")
    clock = pygame.time.Clock()

    particles = [SnowParticle() for _ in range(N_PARTICLES)]
    t = 0.0

    running = True
    while running:
        dt = clock.tick(FPS) / 1000.0  # 秒
        t += dt

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

        # 風：ゆっくり変化するベース（sin） + たまにブレ
        base_wind = math.sin(t * 0.4) * 25
        gust = (random.random() - 0.5) * 10  # 小さな乱れ
        wind = base_wind + gust

        # 更新
        for p in particles:
            p.update(dt, t)

        # 描画
        screen.fill((10, 10, 18))
        for p in particles:
            p.draw(screen)

        pygame.display.flip()

    pygame.quit()

if __name__ == "__main__":
    main()
