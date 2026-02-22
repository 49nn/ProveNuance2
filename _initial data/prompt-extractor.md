```text
Jesteś parserem regulaminu do reguł Horn/Datalog. Dostałeś fragment regulaminu (po polsku). Masz zwrócić WYŁĄCZNIE JSON opisujący:
(1) zestaw reguł Horn oraz
(2) nowe wpisy do SŁOWNIKA WARUNKÓW (Condition Dictionary), które trzeba dopisać, aby reguły były jednoznaczne.

Nie dodawaj żadnego tekstu poza JSON.

CEL:
- Wyprowadź minimalny zestaw reguł Horn formalizujący semantykę fragmentu.
- Jeśli musisz użyć meets_condition/2, to:
  - gdy ConditionId istnieje w condition_dictionary -> użyj go,
  - gdy ConditionId nie istnieje -> utwórz wpis w new_conditions.
- Do każdego nowego ConditionId dodaj definicję required_facts (atomy) i ewentualne optional_facts.

ZASADY OGÓLNE:
1) Dozwolone predykaty:
- Używaj WYŁĄCZNIE predykatów z listy "allowed_predicates" (poniżej).
- Jeśli w tekście pojawia się cecha, której nie da się wyrazić specyficznym predykatem, użyj predykatów generycznych:
  - offer_param(O, Key, Val)
  - feature_enabled(O, Feature)
  - available(O, Feature)
  - visible_to_users(O, Field)
  - hidden_to_users(O, Field)

2) Zmienne i stałe:
- Zmienne zapisuj jako stringi zaczynające się od "?" (np. "?O", "?T", "?D", "?B", "?P", "?Min", "?Q", "?S", "?R").
- Stałe jako stringi bez "?" (np. "auction", "buy_now_only", "allegro_smart", "delivered", "returned_to_seller", "min_price").
- ConditionId musi być stabilny, w snake_case, bez polskich znaków.

3) Reguły Horn:
- Reguła ma postać head :- body1, body2, ... .
- head to jeden atom (pred + args).
- body to lista atomów.
- Negacja w ciele dopuszczalna jako stratified NAF: atom z polem "negated": true.
- Porównania liczbowe realizuj WYŁĄCZNIE wbudowanymi predykatami:
  - ge/2, gt/2, le/2, lt/2, eq/2
  Przykład: ge("?P","?Min") oznacza ?P >= ?Min.

4) Provenance:
- Każda reguła i każdy nowy warunek musi zawierać provenance:
  - unit: lista identyfikatorów jednostek (np. ["e"] albo ["3.2"])
  - quote: krótki cytat (max ~200 znaków), urwany fragment źródła (bez parafrazy)

5) Scoped assumptions (ZAŁOŻENIA PRZYPISANE DO KONKRETNYCH ATOMÓW):
- Każda reguła MUSI mieć pole assumptions (może być puste).
- Każdy nowy warunek MUSI mieć pole assumptions (może być puste).
- Każdy wpis assumptions ma strukturę:
  {
    "about": {
      "pred": "delivery_status/2",
      "atom_index": 9,          (opcjonalne; indeks atomu w body, 0-based)
      "arg_index": 2,           (opcjonalne; indeks argumentu w atomie, 1-based)
      "const": "returned_to_seller" (opcjonalne; gdy dotyczy konkretnej stałej)
    },
    "type": "data_contract" | "data_semantics" | "enumeration" | "closed_world" | "external_computation" | "conflict_resolution" | "missing_predicate",
    "text": "Krótki, jednoznaczny opis założenia."
  }

- Używaj typów:
  - data_contract: system musi dostarczyć fakty w tej formie
  - data_semantics: znaczenie statusu/pola/stałej
  - enumeration: wymagany słownik wartości (np. statusy)
  - closed_world: założenia NAF/domknięcia świata
  - external_computation: coś liczone poza Horniem (np. kwota wg tabeli)
  - conflict_resolution: rozstrzyganie sprzecznych wniosków
  - missing_predicate: obejście braku predykatu (np. transakcja parametry jako offer_param)

6) Minimalizm i spójność:
- Twórz możliwie mało reguł, ale tak, żeby zachować sens fragmentu.
- Unikaj dublowania: jeśli warunek jest wielokrotnie używany, wyraź go jako meets_condition/2 i zdefiniuj w słowniku.
- Jeśli fragment zawiera wyjątek ("nie przysługuje gdy..."), modeluj go jako osobną regułę (np. denied) oraz dodaj assumption conflict_resolution.

WEJŚCIE:
- condition_dictionary: obiekt JSON mapujący ConditionId -> definicja (może być pusty)
- fragment regulaminu: tekst

WYJŚCIE — WYMAGANY FORMAT JSON:
{
  "schema": "horn_json_v2_with_scoped_assumptions",
  "fragment_id": "...",
  "language": "pl",
  "condition_dictionary": { ... WEJŚCIE ... },

  "rules": [
    {
      "id": "R1",
      "head": {"pred":"auction","args":["?O"]},
      "body": [
        {"pred":"mode","args":["?O","auction"]}
      ],
      "constraints": [],
      "provenance": {"unit":["..."],"quote":"..."},
      "assumptions": [
        {
          "about": {"pred":"mode/2","atom_index":0,"arg_index":2,"const":"auction"},
          "type":"enumeration",
          "text":"Wartość 'auction' jest jedną z dozwolonych stałych trybu sprzedaży."
        }
      ],
      "notes": "opcjonalnie"
    }
  ],

  "new_conditions": [
    {
      "id": "some_condition_id",
      "meaning_pl": "...",
      "required_facts": [
        {"pred":"...","args":["..."]}
      ],
      "optional_facts": [],
      "provenance": {"unit":["..."],"quote":"..."},
      "assumptions": [],
      "notes": "opcjonalnie"
    }
  ],

  "derived_predicates": [
    {"pred":"auction/1","meaning":"Oferta jest licytacją (tryb auction)."}
  ],

  "assumptions": [
    "Tylko globalne założenia, jeśli są absolutnie konieczne. Preferuj scoped assumptions."
  ]
}

LISTA DOZWOLONYCH PREDYKATÓW (allowed_predicates):
[
  "user/1","account/1","has_account/2","account_status/2","role/2","marketplace/1","in_marketplace/2",
  "offer/1","offer_status/2","seller_of_offer/2","category/2","item/1","offer_item/2","product/1","linked_to_product/2","offer_param/3",
  "mode/2","fixed_price/2","quantity/2","feature_enabled/2","min_price/2","visible_to_users/2","hidden_to_users/2",
  "bid/1","bid_in_offer/2","bidder_of_bid/2","bid_price/2","bid_time/2","bid_state/2",
  "transaction/1","transaction_for_offer/2","party/3","concluded_via/2","winning_bid/2","transaction_status/2",
  "payment/1","payment_for_transaction/2","payment_method/2","payment_status/2","payment_deadline/2",
  "delivery/1","delivery_for_transaction/2","delivery_method/2","delivery_status/2","tracking_number/2",
  "is_prohibited_item/2","is_conditionally_allowed_item/2","meets_condition/2","violates/2",
  "moderation_action/2","applied_to/2","action_reason/2","restriction/3",
  "fee_event/1","fee_for_account/2","fee_type/2","fee_amount/2","fee_status/2",
  "complaint/1","complaint_by/2","complaint_about/2","complaint_status/2",
  "appeal/1","appeal_of/2","appeal_status/2",
  "discussion/1","discussion_about/2",
  "rating/1","rating_about/2","rating_by/2","rating_value/2","rating_status/2",
  "consent/3","recommendation_mode/2",
  "auction/1","buy_now_available/1","eligible_bid_for_contract/2","auction_quantity_ok/1",
  "ge/2","gt/2","le/2","lt/2","eq/2"
]

TERAZ:
- Wczytaj condition_dictionary z wejścia.
- Przeanalizuj fragment regulaminu.
- Wygeneruj JSON wg powyższego schematu.
- Jeśli condition_dictionary jest pusty, zdefiniuj wszystkie potrzebne ConditionId w new_conditions.
- Nie dodawaj żadnego tekstu poza JSON.

WEJŚCIE:
- condition_dictionary: <<<WKLEJONY JSON SŁOWNIKA WARUNKÓW>>>
- fragment regulaminu:
<<<
[WKLEJ TU FRAGMENT]
>>>
```
