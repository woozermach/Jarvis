# -*- coding: utf-8 -*-
"""Создаёт installer/languages.iss: языки мастера (только те, что есть в установленном Inno Setup) + их строки."""
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

inno = Path(sys.argv[1] if len(sys.argv) > 1 else r"C:\Program Files (x86)\Inno Setup 6")
MSG = {  # имя в Inno: (файл, «удалить данные?», «запустить»)
    "russian": ("Russian", "Удалить также настройки и данные Sayro (ключ API, заметки, память, историю)?", "Запустить Sayro"),
    "ukrainian": ("Ukrainian", "Видалити також налаштування та дані Sayro (ключ API, нотатки, пам'ять, історію)?", "Запустити Sayro"),
    "german": ("German", "Auch Ihre Sayro-Einstellungen und -Daten löschen (API-Schlüssel, Notizen, Gedächtnis, Verlauf)?", "Sayro starten"),
    "french": ("French", "Supprimer aussi vos réglages et données Sayro (clé API, notes, mémoire, historique) ?", "Lancer Sayro"),
    "spanish": ("Spanish", "¿Eliminar también la configuración y los datos de Sayro (clave API, notas, memoria, historial)?", "Iniciar Sayro"),
    "italian": ("Italian", "Eliminare anche impostazioni e dati di Sayro (chiave API, note, memoria, cronologia)?", "Avvia Sayro"),
    "polish": ("Polish", "Usunąć także ustawienia i dane Sayro (klucz API, notatki, pamięć, historię)?", "Uruchom Sayro"),
    "czech": ("Czech", "Odstranit také nastavení a data Sayro (klíč API, poznámky, paměť, historii)?", "Spustit Sayro"),
    "slovak": ("Slovak", "Odstrániť aj nastavenia a údaje Sayro (kľúč API, poznámky, pamäť, históriu)?", "Spustiť Sayro"),
}
langs = ['Name: "english"; MessagesFile: "compiler:Default.isl"']
msgs = []
for name, (fn, delete, start) in MSG.items():
    for cand in (inno / "Languages" / f"{fn}.isl", inno / "Languages" / "Unofficial" / f"{fn}.isl"):
        if cand.exists():
            rel = cand.relative_to(inno).as_posix().replace("/", "\\")
            langs.append(f'Name: "{name}"; MessagesFile: "compiler:{rel}"')
            msgs += [f"{name}.DeleteData={delete}", f"{name}.StartAfter={start}"]
            break
    else:
        print("нет языка:", fn)
out = Path(__file__).with_name("languages.iss")
# Inno 6 читает .iss в UTF-8 с BOM
out.write_text("\n".join(langs) + "\n\n[CustomMessages]\n" + "\n".join(msgs) + "\n", encoding="utf-8-sig")
print(out.read_text(encoding="utf-8-sig"))
