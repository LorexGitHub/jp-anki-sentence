import httpx, json

resp = httpx.post('http://127.0.0.1:8765', json={'action': 'deckNames', 'version': 6})
decks = resp.json().get('result', [])
print('Decks:', json.dumps(decks, ensure_ascii=True))

for deck in decks:
    q = f'deck:"{deck}"'
    resp = httpx.post('http://127.0.0.1:8765', json={'action': 'findCards', 'version': 6, 'params': {'query': q}})
    card_ids = resp.json().get('result', [])
    if card_ids:
        resp = httpx.post('http://127.0.0.1:8765', json={'action': 'cardsInfo', 'version': 6, 'params': {'cards': card_ids[:5]}})
        cards = resp.json().get('result', [])
        models = set()
        for c in cards:
            if 'modelName' in c:
                models.add(c['modelName'])
        print(f'{deck}: {models if models else "empty"}')
    else:
        print(f'{deck}: (no cards)')
