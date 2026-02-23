# ProveNuance2 - dokumentacja projektu

## 1. Cel projektu
ProveNuance2 zamienia treść regulaminów na ustrukturyzowaną wiedzę logiczną, którą można dalej analizować i automatyzować. Projekt łączy trzy warstwy:
- model danych logicznych (predykaty, warunki, reguły),
- persystencję tych danych w bazie,
- ekstraktor, który przetwarza dokumenty i przygotowuje materiał do wnioskowania.

## 2. Architektura w skrócie
Przepływ danych:
1. Dokument PDF jest dzielony na sekcje (spany dokumentu).
2. Sekcje są zapisywane jako uporządkowany materiał źródłowy.
3. Dla wybranej domeny pobierany jest słownik dostępnych predykatów.
4. Ekstraktor buduje kontekst i generuje wynik w postaci reguł, warunków oraz nowych predykatów pochodnych.

W praktyce projekt rozdziela odpowiedzialności:
- `data_model`: wspólny język danych logicznych,
- `db`: utrwalanie definicji i treści dokumentów,
- `pdf` + `llm_query`: ekstrakcja treści i przekształcenie jej do formatu reguł.

## 3. Struktury danych
Projekt operuje na kilku głównych obiektach:

### 3.1 Predykat
Podstawowa jednostka semantyczna domeny. Predykaty opisują:
- fakty wejściowe (np. stan encji),
- fakty wyprowadzane (wnioski),
- ograniczenia użycia (gdzie predykat może się pojawić).

Każdy predykat ma też przypisaną domenę (ogólna lub branżowa), co pozwala budować kontekst adekwatny do typu regulaminu.

### 3.2 Reguła
Reguła opisuje zależność: z jakich przesłanek wynika dana konkluzja. Oprócz logiki zawiera ślad źródłowy (z jakiego fragmentu dokumentu pochodzi) oraz ewentualne założenia interpretacyjne.

### 3.3 Warunek
Warunek grupuje wymagane i opcjonalne fakty pod jedną nazwą biznesową. Dzięki temu można spójnie wykorzystywać te same kryteria w wielu regułach i dokumentach.

### 3.4 Pochodzenie i założenia
Wyniki ekstrakcji nie są „anonimowe”:
- każdy element może wskazywać źródło w dokumencie,
- założenia są jawnie zapisane, aby odróżnić treść normatywną od interpretacji.

### 3.5 Span dokumentu
Dokument jest reprezentowany jako drzewo sekcji. Każda sekcja ma identyfikator jednostki (np. artykuł/punkt) oraz treść. To jest warstwa pośrednia między surowym PDF a logiką reguł.

## 4. Persystencja
Warstwa persystencji przechowuje dwa kluczowe rodzaje danych:

### 4.1 Słownik predykatów i politykę użycia
W bazie utrwalane są definicje predykatów oraz zasady ich dopuszczalności. To stanowi „kontrakt semantyczny” dla ekstraktora i dalszej walidacji.

### 4.2 Spany dokumentów
Po przetworzeniu PDF sekcje dokumentu są zapisywane w postaci umożliwiającej:
- ponowne użycie bez ponownego parsowania PDF,
- precyzyjne odwoływanie się do źródeł podczas budowy reguł.

Model persystencji jest przygotowany do pracy iteracyjnej: można wielokrotnie aktualizować słownik predykatów i ponawiać ekstrakcję dla tych samych dokumentów.

## 5. Ekstraktor
Ekstraktor działa dwuetapowo:

### 5.1 Ekstrakcja struktury dokumentu
Warstwa PDF rozpoznaje sekcje i oczyszcza treść z elementów technicznych (np. szum układu strony), tak aby zachować sens merytoryczny i hierarchię dokumentu.

### 5.2 Ekstrakcja reguł
Warstwa zapytań do modelu językowego buduje kontekst z:
- listy dopuszczonych predykatów,
- istniejących warunków,
- fragmentu regulaminu.

Wynikiem jest ustrukturyzowany pakiet obejmujący:
- reguły,
- nowe definicje warunków,
- predykaty pochodne.

Całość jest projektowana tak, aby wynik był możliwy do audytu i dalszej automatycznej obróbki.

## 6. Typowy scenariusz użycia
1. Zasilenie słownika predykatów (inicjalizacja bazy).
2. Parsowanie regulaminu do spanów i zapis źródeł.
3. Wygenerowanie kontekstu ekstraktora dla wybranej domeny.
4. Uzyskanie reguł i warunków z modelu językowego.
5. Przegląd merytoryczny oraz dalsze użycie wyników w logice biznesowej.

## 7. Granice i odpowiedzialność
- Projekt formalizuje treść regulaminu, ale nie zastępuje oceny prawnej.
- Założenia interpretacyjne są częścią wyniku i powinny być zatwierdzane przez właściciela domeny.
- Jakość ekstrakcji zależy od jakości źródłowego dokumentu i spójności słownika predykatów.
