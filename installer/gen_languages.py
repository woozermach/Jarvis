# -*- coding: utf-8 -*-
"""Создаёт installer/languages.iss: языки мастера (только те, что есть в установленном Inno Setup) + их строки."""
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

inno = Path(sys.argv[1] if len(sys.argv) > 1 else r"C:\Program Files (x86)\Inno Setup 6")
MSG = {  # имя в Inno: (файл, «удалить данные?», «запустить»)
    "russian": ("Russian", "Удалить также настройки и данные Oswin (ключ API, заметки, память, историю)?", "Запустить Oswin"),
    "ukrainian": ("Ukrainian", "Видалити також налаштування та дані Oswin (ключ API, нотатки, пам'ять, історію)?", "Запустити Oswin"),
    "german": ("German", "Auch Ihre Oswin-Einstellungen und -Daten löschen (API-Schlüssel, Notizen, Gedächtnis, Verlauf)?", "Oswin starten"),
    "french": ("French", "Supprimer aussi vos réglages et données Oswin (clé API, notes, mémoire, historique) ?", "Lancer Oswin"),
    "spanish": ("Spanish", "¿Eliminar también la configuración y los datos de Oswin (clave API, notas, memoria, historial)?", "Iniciar Oswin"),
    "italian": ("Italian", "Eliminare anche impostazioni e dati di Oswin (chiave API, note, memoria, cronologia)?", "Avvia Oswin"),
    "polish": ("Polish", "Usunąć także ustawienia i dane Oswin (klucz API, notatki, pamięć, historię)?", "Uruchom Oswin"),
    "czech": ("Czech", "Odstranit také nastavení a data Oswin (klíč API, poznámky, paměť, historii)?", "Spustit Oswin"),
    "slovak": ("Slovak", "Odstrániť aj nastavenia a údaje Oswin (kľúč API, poznámky, pamäť, históriu)?", "Spustiť Oswin"),
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
