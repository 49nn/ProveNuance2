Podział praktyczny jest taki: **predykaty faktów** opisują stan/zdarzenia w systemie (input), a **predykaty reguł** to wnioski/klasyfikacje/decyzje (output) oraz pomocnicze „agregaty” liczone z faktów. Ten sam predykat *może* wystąpić po obu stronach (np. `violates/2` bywa faktem z detektora albo wnioskiem z reguł), ale na start warto rozdzielić.

Poniżej rozpisuję dla minimalnego schematu.

---

## 1) Predykaty faktów (wejściowe, „dane z systemu”)

### Podmioty i kontekst

* `user/1`
* `account/1`
* `has_account/2`
* `account_status/2`
* `role/2`
* `marketplace/1`
* `in_marketplace/2`

### Oferty i towar

* `offer/1`
* `offer_status/2`
* `seller_of_offer/2`
* `category/2`
* `item/1`
* `offer_item/2`
* `product/1`
* `linked_to_product/2` *(jeśli system to trzyma; jeśli nie, to może być wniosek)*
* `offer_param/3` *(parametry z formularza/produktów)*

### Konfiguracja trybu sprzedaży

* `mode/2`
* `fixed_price/2`
* `quantity/2`
* `feature_enabled/2`
* `min_price/2`

### Zdarzenia licytacji

* `bid/1`
* `bid_in_offer/2`
* `bidder_of_bid/2`
* `bid_price/2`
* `bid_time/2` *(jeżeli potrzebujesz „pierwszej oferty” / terminów)*
* `bid_state/2`

### Transakcje i przebieg

* `transaction/1`
* `transaction_for_offer/2`
* `party/3`
* `concluded_via/2` *(często fakt z systemu; może też być wniosek)*
* `winning_bid/2` *(zwykle fakt z silnika aukcji; może być wniosek)*
* `transaction_status/2`

### Płatności i zwroty

* `payment/1`
* `payment_for_transaction/2`
* `payment_method/2`
* `payment_status/2`
* `payment_deadline/2`
* `refund/1`
* `refund_for_transaction/2`
* `refund_status/2`

### Dostawa

* `delivery/1`
* `delivery_for_transaction/2`
* `delivery_method/2`
* `delivery_status/2`
* `tracking_number/2`

### Zgodność i katalogi zakazów (często dane referencyjne)

* `is_prohibited_item/2`
* `is_conditionally_allowed_item/2`
* `meets_condition/2` *(np. „sprzedawca zweryfikowany”, „kategoria wymaga X”)*
* `ranking_signal/3` *(jeśli modelujesz ranking; w wielu wdrożeniach zbędne)*

### Moderacja jako zdarzenia/fakty

* `moderation_action/2`
* `applied_to/2`
* `action_reason/2`
* `restriction/3` *(stan ograniczeń może być faktem lub wnioskiem; zwykle fakt z systemu)*

### Opłaty

* `fee_event/1`
* `fee_for_account/2`
* `fee_type/2`
* `fee_amount/2`
* `fee_status/2`

### Reklamacje/odwołania/dyskusje

* `complaint/1`
* `complaint_by/2`
* `complaint_about/2`
* `complaint_status/2`
* `appeal/1`
* `appeal_of/2`
* `appeal_status/2`
* `discussion/1`
* `discussion_about/2`

### Oceny

* `rating/1`
* `rating_about/2`
* `rating_by/2`
* `rating_value/2`
* `rating_status/2`

### Prywatność / personalizacja

* `consent/3`
* `recommendation_mode/2`

---

## 2) Predykaty reguł (wnioski/decyzje + „pomocnicze agregaty”)

### Klasyfikacje i walidacje (outputs)

* `auction/1` *(z `mode/2`)*
* `buy_now_only/1` *(z `mode/2`)*
* `offer_valid/1` / `offer_invalid/2` *(powód walidacji)*
* `auction_quantity_ok/1` *(3.1(b))*
* `eligible_bid_for_contract/2` *(3.2)*
* `contract_possible/1` / `contract_blocked/2`
* `can_conclude_via_buy_now/1` *(zależne od okna czasowego/zdarzeń)*

### Dostępność funkcji i okna czasowe

* `buy_now_available/1` *(3.1(b) + 3.2)*
* `feature_available/2` *(ogólniej, zamiast wielu predykatów)*
* `deadline_passed/2` *(pomocnicze, jeśli masz czas)*

### Widoczność informacji (UI)

* `hidden_to_users/2` / `visible_to_users/2` *(mogą być wnioskiem z reguł; stan w UI bywa też faktem – zależy od architektury)*
* `should_display/2` / `should_hide/2` *(jeśli chcesz rozdzielić normę od realizacji UI)*

### Naruszenia i sankcje (jeśli wnioskujesz je z reguł)

* `violates/2` *(często wniosek: „narusza regułę X”)*
* `should_apply_sanction/2` *(kogo i jaką)*
* `should_remove_offer/2`
* `should_suspend_account/2`
* `should_limit_feature/3`

### Rozstrzygnięcia w sporach/procedurach (jeśli formalizujesz)

* `complaint_eligible/2` *(np. czy skarga spełnia warunki)*
* `appeal_eligible/2`
* `requires_manual_review/2` *(flag, gdy reguły nie rozstrzygają)*

---

## 3) Predykaty „na granicy” (zależy od źródła danych)

Te predykaty mogą być:

* **faktami**, jeśli system je już wylicza i zapisuje,
* albo **wnioskami**, jeśli chcesz je liczyć z reguł.

Najczęstsze:

* `winning_bid/2` (system aukcyjny zwykle daje fakt)
* `concluded_via/2` (fakt operacyjny)
* `linked_to_product/2` (fakt, jeśli platforma wymusza linkowanie; wniosek, jeśli inferujesz z `offer_param/3`)
* `restriction/3` (fakt stanu konta, ale reguły mogą sugerować `should_limit_feature/3`)
* `violates/2` (fakt z detektora/ML, albo wniosek z reguł)

---

## 4) Reguła praktyczna: co jest faktem, a co regułą

**Fakty** to to, co:

* pochodzi z bazy operacyjnej / logów zdarzeń,
* jest mierzalne (czas, cena, status),
* jest konfiguracją użytkownika/sprzedawcy.

**Wnioski (reguły)** to to, co:

* odpowiada na pytania normatywne („czy wolno”, „czy dostępne”, „czy jawne”, „czy skutkuje umową”),
* klasyfikuje i waliduje,
* generuje decyzje moderacyjne (rekomendacja akcji) lub obowiązki.
