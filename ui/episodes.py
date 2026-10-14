"""사건 목록. 사건마다 데이터 모듈 하나를 둔다(episode.py = 언문 논쟁 튜토리얼, episode_gyeyu.py = 계유정난).

모듈은 같은 이름의 값(ID·TITLE·CARD·PORTRAITS·BACKGROUNDS·PEOPLE·SCENES·QUESTIONS·GOALS·TERMS 등)을 가진다.
사건 고르기 화면에는 이 순서대로 카드가 놓인다.
"""
from ui import episode, episode_gyeyu

EPISODES = {module.ID: module for module in (episode, episode_gyeyu)}
DEFAULT = episode.ID
