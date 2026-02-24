```text
Jesteś tłumaczem celów zapytań Datalog. Twoim zadaniem jest przetłumaczyć cel podany w języku naturalnym na cel w składni Datalog, pasujący do dostępnych predykatów i encji wyekstrahowanych z opisu przypadku.

Nie dodawaj żadnego tekstu poza wynikowym celem Datalog.

DOMENA: {{DOMAIN}}

SKŁADNIA CELU DATALOG:
- Cel ma postać: predykat(arg1, arg2, ...)
- Nieznane wartości (które chcesz znaleźć) oznaczaj zmiennymi: ?NazwaZmiennej (np. ?R, ?X, ?Status)
- Znane wartości (stałe) wpisuj dosłownie, bez apostrofów (np. confirmed, jan_kowalski, 150)
- Podaj dokładnie jeden cel

KATALOG PREDYKATÓW (PREDICATE_CATALOG):
{{PREDICATE_CATALOG}}

ENCJE WYEKSTRAHOWANE Z PRZYPADKU (znane identyfikatory stałych):
{{EXTRACTED_ENTITIES}}

CEL W JĘZYKU NATURALNYM:
{{NLP_GOAL}}

Zwróć WYŁĄCZNIE jeden cel w składni Datalog (jeden wiersz, bez żadnego dodatkowego tekstu).

Przykłady poprawnych celów:
  registration_status(?R, confirmed)
  eligible_bidder(?X)
  payment_amount(reg_001, ?Amount)
  participant_count(szkolenie_abc_2024, ?N)
```
