from types import SimpleNamespace

from o2j import post_rules as PR


def _doc(text):
    return SimpleNamespace(pages=[SimpleNamespace(text=text)])


def test_city_diacritics_restored():
    r = {"OdwolanieKIO": {"miejscowosc": "Lódź"}}
    PR.apply(r, None)
    assert r["OdwolanieKIO"]["miejscowosc"] == "Łódź"
    r = {"OdwolanieKIO": {"miejscowosc": "Warszawa"}}
    assert PR.apply(r, None) == [] and r["OdwolanieKIO"]["miejscowosc"] == "Warszawa"
    r = {"OdwolanieKIO": {"miejscowosc": "Brzozowiec"}}  # unknown town: untouched
    assert PR.apply(r, None) == []


def test_shared_regon_stays_with_nearest_party():
    text = ("Zamawiający: Zarząd Dróg Powiatowych w Brzozowcu, NIP 999-239-80-73, prowadzący postępowanie, "
            "oraz Zakład Gospodarki Komunalnej w Zielonkowie, REGON 999806152.")
    r = {"Zamawiajacy": [{"nazwa": "Zarząd Dróg Powiatowych w Brzozowcu", "nip": "9992398073", "regon": "999806152"},
                         {"nazwa": "Zakład Gospodarki Komunalnej w Zielonkowie", "nip": None, "regon": "999806152"}]}
    PR.apply(r, _doc(text))
    assert r["Zamawiajacy"][0]["regon"] is None and r["Zamawiajacy"][1]["regon"] == "999806152"


def test_shared_id_untouched_without_evidence():
    r = {"Zamawiajacy": [{"nazwa": "A Sp. z o.o.", "regon": "123456789"}, {"nazwa": "B S.A.", "regon": "123456789"}]}
    PR.apply(r, _doc("tekst bez numerów"))
    assert r["Zamawiajacy"][0]["regon"] == "123456789" == r["Zamawiajacy"][1]["regon"]


def test_stamp_date_replaced_by_labelled_operation_date():
    text = "Kwota 34,00 PLN Data transakcji 20.05.2026 Numer CEN1 Dokument wygenerowany w dniu 20.05.2026 WPŁYNĘŁO dnia 16.05.2026 L.dz. 380"
    r = {"przelew_bankowy": {"data_operacji": "2026-05-16"}}
    PR.apply(r, _doc(text))
    assert r["przelew_bankowy"]["data_operacji"] == "2026-05-20"


def test_operation_date_kept_when_not_only_in_stamp():
    text = "Data operacji 16.05.2026 Data księgowania 17.05.2026 WPŁYNĘŁO dnia 16.05.2026"
    r = {"przelew_bankowy": {"data_operacji": "2026-05-16"}}
    assert PR.apply(r, _doc(text)) == [] and r["przelew_bankowy"]["data_operacji"] == "2026-05-16"


def test_sole_trader_is_natural_person():
    text = "Ja, niżej podpisany/a Paweł Brzozowski, prowadzący/a działalność gospodarczą pod firmą Paweł Brzozowski Asterion Usługi Techniczne, NIP 999-663-55-12"
    r = {"mocodawca": [{"data": {"imie_nazwisko": None, "nazwa": "Paweł Brzozowski Asterion Usługi Techniczne",
                                 "typ": "osoba_prawna", "nip": "9996635512", "krs": None}}]}
    PR.apply(r, _doc(text))
    d = r["mocodawca"][0]["data"]
    assert d["typ"] == "osoba_fizyczna" and d["imie_nazwisko"] == "Paweł Brzozowski"


def test_company_untouched():
    text = "Asterion Budownictwo sp. k. z siedzibą w Lublinie, reprezentowana przez Jana Kowalskiego"
    r = {"mocodawca": [{"data": {"nazwa": "Asterion Budownictwo sp. k.", "typ": "osoba_prawna", "imie_nazwisko": None}}]}
    assert PR.apply(r, _doc(text)) == []


def test_account_country_code_kept_when_in_document():
    text = "Z rachunku: PL62 2170 0008 9152 5017 5661 7062 Na rachunek: 60 1010 1010 0078 2422 3100 0000"
    r = {"przelew_bankowy": {"z_rachunku": "62217000089152501756617062", "na_rachunek": "60101010100078242231000000"}}
    PR.apply(r, _doc(text))
    assert r["przelew_bankowy"]["z_rachunku"] == "PL62217000089152501756617062"
    assert r["przelew_bankowy"]["na_rachunek"] == "60101010100078242231000000"


def test_account_prefix_removed_when_not_in_document():
    r = {"przelew_bankowy": {"z_rachunku": "PL62217000089152501756617062"}}
    PR.apply(r, _doc("Z rachunku 62 2170 0008 9152 5017 5661 7062"))
    assert r["przelew_bankowy"]["z_rachunku"] == "62217000089152501756617062"
