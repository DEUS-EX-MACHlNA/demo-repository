# Night Test

### 초기 메모리 반영

DEBUG:app.agents.memory:add_memory: npc=family type=observation importance=7.0 total_acc=7.0
DEBUG:app.agents.memory:add_memory: npc=partner type=observation importance=6.0 total_acc=6.0
DEBUG:app.agents.memory:add_memory: npc=witness type=observation importance=6.0 total_acc=6.0

### Family 초기 목표 설정

DEBUG:app.agents.planning:long_term_plan: npc=family plan='**전체적인 목표:** 진실을 밝히고 정의를 실현하여 가해자가 책임을 지도록 하며, 동시에 가족의 슬픔과 상...'
DEBUG:app.agents.retrieval:retrieve_memories: query='피해자 가족의 다음 행동 계획...' returned 1 memories
DEBUG:app.agents.planning:short_term_plan: npc=family plan='다음 턴에는 질문의 내용을 자세히 듣고, 그 질문이 증거 수집이나 진실 규명에 어떻게 도움이 될 수 있는지 ...'
DEBUG:app.agents.memory:add_memory: npc=family type=plan importance=8.0 total_acc=15.0

DEBUG:__main__:[GA Night] plan: npc=family, plan='다음 턴에는 질문의 내용을 자세히 듣고, 그 질문이 증거 수집이나 진실 규명에 어떻게 도움...'

### Partner 초기 목표 설정

DEBUG:app.agents.planning:long_term_plan: npc=partner plan='전체적인 목표는 사건의 진실을 객관적이고 재현 가능한 증거에 기반하여 밝히는 것입니다. 이를 위해 현재 턴에...'
DEBUG:app.agents.retrieval:retrieve_memories: query='동료 수사관의 다음 행동 계획...' returned 1 memories
DEBUG:app.agents.planning:short_term_plan: npc=partner plan='다음 턴에는 목격자들을 대상으로 추가 인터뷰를 진행할 계획입니다. 특히, 피해자 가족의 진술과 일치하거나 모...'
DEBUG:app.agents.memory:add_memory: npc=partner type=plan importance=8.0 total_acc=14.0

DEBUG:__main__:[GA Night] plan: npc=partner, plan='다음 턴에는 목격자들을 대상으로 추가 인터뷰를 진행할 계획입니다. 특히, 피해자 가족의 진...'

### Witness 초기 목표 설정

DEBUG:app.agents.planning:long_term_plan: npc=witness plan='목표: 주요 사건에 대한 직접적인 연루나 확신을 피하면서 안전하게 상황을 통과하고, 필요할 때 모호한 증언으...'
DEBUG:app.agents.retrieval:retrieve_memories: query='목격자의 다음 행동 계획...' returned 1 memories
DEBUG:app.agents.planning:short_term_plan: npc=witness plan='다음 턴에는 질문의 맥락을 주의 깊게 살펴보겠습니다. 만약 추궁하는 톤이 감지되면, 일시적인 혼란을 가장하여...'
DEBUG:app.agents.memory:add_memory: npc=witness type=plan importance=8.0 total_acc=14.0

DEBUG:__main__:[GA Night] plan: npc=witness, plan='다음 턴에는 질문의 맥락을 주의 깊게 살펴보겠습니다. 만약 추궁하는 톤이 감지되면, 일시적...'

### 대화 시작 - witness, family

INFO:__main__:[GA Night] dialogue pairs: [('witness', 'family')]

DEBUG:app.agents.retrieval:retrieve_memories: query='피해자 가족와(과) 대화...' returned 2 memories
DEBUG:app.agents.retrieval:retrieve_memories: query='목격자와(과) 대화...' returned 2 memories
DEBUG:app.agents.retrieval:retrieve_memories: query='피해자 가족와(과) 대화...' returned 2 memories
DEBUG:app.agents.retrieval:retrieve_memories: query='목격자와(과) 대화...' returned 2 memories
INFO:app.agents.dialogue:dialogue: 목격자 <-> 피해자 가족, 4 utterances

DEBUG:app.agents.memory:add_memory: npc=witness type=dialogue importance=7.0 total_acc=21.0
DEBUG:app.agents.memory:add_memory: npc=family type=dialogue importance=7.0 total_acc=22.0
DEBUG:app.agents.dialogue:conversation_impact: {'witness': {}, 'family': {}}
INFO:__main__:[GA Night] done: conversations=1, is_observed=False

============================================================
night_delta: {'turn_increment': 1, 'npc_stats': {'partner': {'suspicion': 1}}, 'vars': {}}
is_observed: False

night_dialogue:
차가운 밤공기 속에서 목격자와 피해자 가족의 대화는 처음엔 조심스럽게 시작되었으나, 시간이 흐를수록 그 목소리에는 점점 더 무거운 그림자가 드리웠다. 조심스럽게 꺼낸 증언 하나하나가 밤의 어둠을 더욱 짙게 만들며, 잊혀진 진실의 조각들이 서로 맞물려 불길한 예감을 증폭시켰다. 대화의 흐름은 점점 더 긴장감으로 가득 찼고, 주변의 조용한 밤은 그들의 이야기에 휩싸여 숨죽이고 있었다.

[family] 기억 수: 3, 계획: 다음 턴에는 질문의 내용을 자세히 듣고, 그 질문이 증거 수집이나 진실 규명에 어떻게 도움...

[partner] 기억 수: 2, 계획: 다음 턴에는 목격자들을 대상으로 추가 인터뷰를 진행할 계획입니다. 특히, 피해자 가족의 진...

[witness] 기억 수: 3, 계획: 다음 턴에는 질문의 맥락을 주의 깊게 살펴보겠습니다. 만약 추궁하는 톤이 감지되면, 일시적...
