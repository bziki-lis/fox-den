#!/usr/bin/env python3
"""Пересчёт виджетов Лисьей обители из выгрузок Notion.

Запуск:  python3 tools/recount.py <папка_с_выгрузками> [--today ГГГГ-ММ-ДД] [--only daily]

В папке лежат JSON-ответы notion-query-data-sources в режиме view (как есть:
{"results": [...], ...}). Страницы одного вида кладутся несколькими файлами
с общим префиксом (media1.json, media2.json, …). Колонки — родные имена свойств Notion.
  media*   — Сокровищница (книги, фильмы, сериалы)   view://7934b2fa-45db-4cc0-8d72-537dfb6a9980
  games*   — Игровые миры                             view://3019421a-357e-4567-b00c-fb2b7a05cf7b
  verstak* — Верстак                                  view://a4ecd60f-404e-4178-8595-806989d0a045
  ach*     — Ачивки                                   view://a809267f-856b-4a2a-8513-6b699a9ec082
  days*    — Дни                                      view://f39e4877-ee90-452a-a884-abbae5fc7fc7
  haos*    — Хаос                                     view://6bf6bb2f-cbd2-4cf8-81bc-1e7fc6577860
Чего нет в папке — того блок не трогаем (старые цифры остаются).
Пишет counters.json, trackers.json, days.json в корне репозитория.
"""
import argparse, collections, datetime as dt, glob, json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEATHER = ['паршиво', 'так себе', 'нормально', 'хорошо', 'ахуенно']   # w = индекс + 1
ENERGY = ['на нуле', 'мало', 'норм', 'через край']                 # e = индекс
RARITY = {'легендарная': 100, 'эпическая': 50, 'редкая': 15}        # иначе 5
DONE_MEDIA = ('закончено', 'любимое')


def load(dirpath, prefix):
    files = sorted(glob.glob(os.path.join(dirpath, prefix + '*.json')))
    if not files:
        return None
    rows = []
    for f in files:
        data = json.load(open(f, encoding='utf-8'))
        rows.extend(data.get('results', []) if isinstance(data, dict) else data)
    return rows


def num(x):
    try:
        return float(x) if x not in (None, '') else 0.0
    except (TypeError, ValueError):
        return 0.0


def jlist(x):
    if isinstance(x, list):
        return x
    try:
        v = json.loads(x or '[]')
        return v if isinstance(v, list) else []
    except (TypeError, ValueError):
        return []


def pid(x):
    m = re.findall(r'[0-9a-f]{32}', (x or '').replace('-', ''))
    return m[-1] if m else None


def rjson(path):
    return json.load(open(path, encoding='utf-8'))


def wjson(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write('\n')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('src')
    ap.add_argument('--today')
    a = ap.parse_args()
    today = dt.date.fromisoformat(a.today) if a.today else dt.date.today()
    T = today.isoformat()
    month = T[:7]
    C = rjson(os.path.join(ROOT, 'counters.json'))
    TR = rjson(os.path.join(ROOT, 'trackers.json'))
    D = rjson(os.path.join(ROOT, 'days.json'))
    log = []

    # ---------- книги ----------
    media = load(a.src, 'media')
    books = screen = None
    if media is not None:
        books = [m for m in media if m.get('Тип') == 'книга' and m.get('Статус') in DONE_MEDIA]
        screen = [m for m in media if (m.get('Тип') == 'фильм' and m.get('Статус') in DONE_MEDIA) or m.get('Тип') == 'сериал']
        pages = audio = py = ay = 0.0
        for b in books:
            tags = jlist(b.get('Теги'))
            note = (b.get('Заметка') or '').lower()
            year = int(num(b.get('Год прочтения'))) if b.get('Год прочтения') else None
            p = num(b.get('Страниц'))
            # аудио считаем, только если реально слушала: чистая аудиокнига
            # или в заметке «прослушана» / «аудиокнига»
            listened = 'аудио' in tags and ('текст' not in tags or 'прослуш' in note or 'аудиокниг' in note)
            h = num(b.get('Аудио (часов)')) if listened else 0.0
            pages += p; audio += h
            if year == today.year:
                py += p; ay += h
        s = C['stranicy']
        s['stats'][0]['value'] = round(pages)
        s['stats'][1]['value'] = round(audio)
        s['py'], s['ay'], s['updated'] = round(py), round(ay), T
        log.append(f'книги: {round(pages)} стр., {round(audio)} ч; за год {round(py)} стр., {round(ay)} ч')

    # ---------- кино ----------
    film_h = series_h = None
    if screen is not None:
        f = [r for r in screen if r.get('Тип') == 'фильм']
        s_ = [r for r in screen if r.get('Тип') == 'сериал']
        films = len(f)
        film_h = sum(num(r.get('Минут')) for r in f) / 60
        series = len(s_)
        eps = sum(num(r.get('Серий просмотрено')) for r in s_)
        series_h = sum(num(r.get('Минут')) * num(r.get('Серий просмотрено')) for r in s_) / 60
        k = C['kino']
        k['stats'][0]['value'], k['stats'][1]['value'], k['stats'][2]['value'] = round(films), round(series), round(eps)
        k['hours'], k['updated'] = round(film_h + series_h), T
        log.append(f'кино: {round(films)} фильмов, {round(series)} сериалов, {round(eps)} серий, {k["hours"]} ч')

    # ---------- игры и трофеи ----------
    games = load(a.src, 'games')
    if games is not None:
        hours = sum(num(g.get('Часы Steam')) for g in games)
        sims = sum(num(g.get('Часы Steam')) for g in games if re.search(r'sims', g.get('Игра') or '', re.I))
        g = C['igry']
        # часы в играх только растут: если в базе цифры старее виджета
        # (свежую выгрузку Steam ещё не внесли в Notion), оставляем большие
        g['value'] = max(round(hours), g.get('value') or 0)
        g['sims'] = max(round(sims), g.get('sims') or 0)
        g['updated'] = T
        g['foot'] = 'из них {sims} — в Симс. Кто бы сомневался'
        full, near = [], []
        for x in games:
            got, tot = num(x.get('Достижения')), num(x.get('Всего достижений'))
            # процент считаем сами: «Прогресс» в базе — формула, а метка «100%» может отставать
            pct = got / tot * 100 if tot else 0
            if (tot and got >= tot) or x.get('Достижения Steam') == '100%':
                full.append([x.get('Игра'), int(tot or got), (x.get('date:Последний запуск:start') or '')[:4]])
            elif tot and 80 <= pct < 100:
                near.append([x.get('Игра'), int(pct), int(got), int(tot)])
        full.sort(key=lambda r: (r[2] or '9999', r[0] or ''))
        near.sort(key=lambda r: -r[1])
        TR['trofei'] = {
            'full': full, 'near': near[:4],
            'earned': int(sum(num(x.get('Достижения')) for x in games)),
            'total': int(sum(num(x.get('Всего достижений')) for x in games)),
            'games': len(games),
        }
        log.append(f'игры: {round(hours)} ч (Симс {round(sims)}); кубков {len(full)}')

    # ---------- время в чужих мирах ----------
    if media is not None or games is not None:
        st = C['stranicy']['stats']
        kh = C['kino'].get('hours') or 0
        total = (C['igry'].get('value') or 0) + kh + (st[1]['value'] or 0) + (st[0]['value'] or 0) / 60
        v = C['vremya']
        v['stats'][0]['value'] = round(total, -1)
        v['years'] = str(round(total / 16 / 365, 1)).replace('.', ',')
        v['updated'] = T

    # ---------- верстак: моды и сад творчества ----------
    verstak = load(a.src, 'verstak')
    weight = {}
    if verstak is not None:
        sad = collections.defaultdict(list)
        mods = 0
        for r in verstak:
            is_tr = r.get('Тип') == 'перевод мода'
            weight[pid(r.get('url'))] = max(1, num(r.get('Версий')) or 1) if is_tr else 0
            if r.get('Статус') != 'опубликовано':
                continue
            if is_tr:
                mods += 1
            d = (r.get('date:Дата публикации:start') or '')[:10]
            if d:
                sad[d].append([r.get('Название') or '', 't' if is_tr else 'o'])
        TR['sad'] = {'days': dict(sorted(sad.items())), 'total': sum(len(v) for v in sad.values())}
        C['perevody']['mods'] = mods
        log.append(f'верстак: {mods} модов, в саду {TR["sad"]["total"]} выпусков')

    # ---------- опыт ----------
    ach = load(a.src, 'ach')
    if ach is not None and verstak is not None:
        cats = collections.Counter()
        for r in ach:
            pts = RARITY.get(r.get('Редкость'), 5)
            w = sum(weight.get(pid(u), 0) for u in jlist(r.get('Из мастерской')))
            cats[r.get('Категория') or 'другое'] += pts * max(1, w)
        o = C['opyt']
        o['xp'], o['cats'], o['updated'] = int(sum(cats.values())), {k: int(v) for k, v in cats.items()}, T
        log.append(f'опыт: {o["xp"]}')
    elif ach is not None:
        log.append('опыт пропущен: нет выгрузки верстака')

    # ---------- дни: погода и баночки ----------
    days = load(a.src, 'days')
    if days is not None:
        out, months = [], collections.defaultdict(lambda: {'n': 0, 'c': collections.Counter()})
        for r in days:
            d = (r.get('date:Дата:start') or '')[:10]
            if not d:
                continue
            rec = {'d': d}
            w = (r.get('Погода внутри') or '')
            for i, name in enumerate(WEATHER):
                if w.endswith(name):
                    rec['w'] = i + 1
            if r.get('Энергия') in ENERGY:
                rec['e'] = ENERGY.index(r.get('Энергия'))
            out.append(rec)
            m = months[d[:7]]
            m['n'] += 1
            for c in jlist(r.get('Забота')):
                m['c'][c] += 1
        D = {'updated': T, 'days': sorted(out, key=lambda x: x['d'])}
        TR['zabota'] = {'months': {k: {'n': v['n'], 'c': dict(v['c'])} for k, v in sorted(months.items())}}
        log.append(f'дни: {len(out)} записей')

    # ---------- хаос: сделано и отпущено ----------
    haos = load(a.src, 'haos')
    if haos is not None:
        done = sum(1 for r in haos if r.get('Статус') == 'Сделано' and (r.get('date:Закрыто:start') or '')[:7] == month)
        let_go = sum(1 for r in haos if r.get('Статус') == 'Отпущено' and (r.get('date:Закрыто:start') or '') >= '2026-10-14')
        s = C['sdelano']
        if s.get('month') != month:
            s['month'], s['drugoe'] = month, 0
        s['haos'] = done
        s['value'] = done + (s.get('drugoe') or 0)
        s['updated'] = T
        o = C['otpuscheno']
        o['n'] = (o.get('n') or 0) - (o.get('haos') or 0) + let_go
        o['haos'], o['updated'] = let_go, T
        log.append(f'сделано в месяце: {s["value"]} (хаос {done}, другое {s.get("drugoe") or 0}); отпущено: {o["n"]}')

    TR['updated'] = T
    wjson(os.path.join(ROOT, 'counters.json'), C)
    wjson(os.path.join(ROOT, 'trackers.json'), TR)
    wjson(os.path.join(ROOT, 'days.json'), D)
    print('\n'.join(log) or 'нечего пересчитывать')


if __name__ == '__main__':
    sys.exit(main())
