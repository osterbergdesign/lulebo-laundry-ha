# Lulebo Tvättstuga för Home Assistant 🧺

En custom integration för att övervaka, boka och avboka tvättpass hos Lulebo (Aptus) direkt i Home Assistant. 

## Funktioner
* 🟢 Se lediga tvättider för veckan.
* 📅 Boka och avboka pass via skript.
* ✅ Fullt integrerad med Home Assistants inbyggda "Att göra"-lista (Todo) för att visa aktiva bokningar.

## Installation via HACS (Rekommenderas)
1. Öppna HACS i Home Assistant.
2. Klicka på de tre prickarna uppe till höger och välj **Custom repositories**.
3. Klistra in länken till detta repo: `https://github.com/DITT_GITHUB_NAMN/lulebo-laundry-ha`
4. Välj kategori: **Integration**.
5. Klicka på "Lägg till" och ladda ner.
6. Starta om Home Assistant.


## Hur du hittar dina ID:n (Contract ID & Booking Group ID)
För att integrationen ska hitta rätt tvättstuga behöver du dina unika ID:n från Lulebos webbplats. Så här hittar du dem på 1 minut:

1. Logga in på **[Lulebo.se](https://www.lulebo.se)** via en dator.
2. Gå till sidan där du brukar boka tvättstugan (Mina Sidor -> Boka Tvättstuga).
3. Tryck på **F12** på tangentbordet för att öppna webbläsarens "Utvecklarverktyg".
4. Klicka på fliken **Network** (Nätverk).
5. Ladda om sidan (F5) och klicka på knappen för att öppna själva tvättstugekalendern.
6. Leta i listan över nätverksanrop efter en länk som heter något i stil med `EngagementLoadLinks` eller `BookingCalendar`.
7. Klicka på den och titta på adressen (URL:en). Där kommer du se dina ID:n i klartext, till exempel:
   `...contractid=nummer...` 
   `...bookingGroupId=nummer...`
8. Kopiera dessa siffror och klistra in dem i Home Assistant när du installerar integrationen!







EXAMPLE AUTOMATIONS AND CARDS

***Booked times card***

type: todo-list
entity: todo.tvattstuga
title: Mina Bokade Pass 🧺
card_mod:
  style: |
    ha-card {
      background: transparent;
      border: none;
      box-shadow: none;
      padding-top: 0px !important;
    }
    ha-textfield {
      display: none !important;
    }
    mwc-button, ha-icon-button[slot="icon"] {
      display: none !important;
    }
    ha-checkbox {
      --mdc-checkbox-unchecked-color: var(--secondary-text-color);
    }


***AVAILABLE TIMES LIST O BOKNINGS LISTA CARD***
**KRÄVER autoentities card**
type: custom:auto-entities
card:
  type: entities
  title: Tvättstuga
filter:
  template: >-
    {% set dates = state_attr('sensor.lulebo_laundry_availability',
    'available_dates') %} {% set bookings =
    state_attr('sensor.lulebo_laundry_availability', 'current_bookings') %} {%
    set ns = namespace(items=[]) %} {% set time_map = {
      '07:00 - 10:30': 0,
      '10:30 - 14:00': 1,
      '14:00 - 17:30': 2,
      '17:30 - 21:00': 3
    } %} {% set sv_weekdays = {
      'Monday': 'Måndag', 'Tuesday': 'Tisdag', 'Wednesday': 'Onsdag', 
      'Thursday': 'Torsdag', 'Friday': 'Fredag', 'Saturday': 'Lördag', 'Sunday': 'Söndag'
    } %}

    {# --- 1. AKTIVA BOKNINGAR (Eller tomrum-status direkt under titeln) --- #}
    {% if bookings %}
      {% for b_date, b_url in bookings.items() %}
        {% set en_weekday = as_timestamp(b_date ~ 'T00:00:00') | timestamp_custom('%A') %}
        {% set weekday = sv_weekdays.get(en_weekday, en_weekday) %}
        {% set ns.items = ns.items + [{
          "type": "button",
          "name": "Bokad: " ~ b_date ~ " (" ~ weekday ~ ")",
          "icon": "mdi:washing-machine-check",
          "action_name": "AVBOKA",
          "tap_action": {
            "action": "call-service",
            "service": "script.execute_laundry_cancellation",
            "service_data": {
              "target_date": b_date
            },
            "confirmation": {
              "text": "Vill du avboka tvättstugan den " ~ b_date ~ "?"
            }
          }
        }] %}
      {% endfor %}
    {% else %}
      {# Visar detta om du inte har något bokat #}
      {% set ns.items = ns.items + [{
        "type": "button",
        "name": "Inga tider bokade",
        "icon": "mdi:calendar-blank",
        "tap_action": {
          "action": "none"
        }
      }] %}
    {% endif %}

    {# --- 2. LEDIGA TIDER DÄRUNDER --- #} {% if dates %}
      {% set ns.items = ns.items + [{
        "type": "section",
        "label": "- - - - - - - - - - - - - - - - - - - - Lediga Tider - - - - - - - - - - - - - - - - - - - -"
      }] %}
      
      {% for date, times in dates.items() %}
        {% if loop.index <= 7 %}
          {% set en_weekday = as_timestamp(date ~ 'T00:00:00') | timestamp_custom('%A') %}
          {% set weekday = sv_weekdays.get(en_weekday, en_weekday) %}
          
          {% set ns.items = ns.items + [{
            "type": "section",
            "label": date ~ " (" ~ weekday ~ ")"
          }] %}
          
          {% for time in times %}
            {% set ns.items = ns.items + [{
              "type": "button",
              "name": time,
              "icon": "mdi:washing-machine",
              "action_name": "BOKA",
              "tap_action": {
                "action": "call-service",
                "service": "script.execute_laundry_booking",
                "service_data": {
                  "booking_date": date,
                  "booking_slot": time_map.get(time, 0)
                },
                "confirmation": {
                  "text": "Vill du boka tvättstugan den " ~ date ~ " kl " ~ time ~ "?"
                }
              }
            }] %}
          {% endfor %}
        {% endif %}
      {% endfor %}
    {% endif %}

    {# --- 3. FALLBACK OM ALLT ÄR TOMT --- #} {% if not dates and not bookings
    %}
      {% set ns.items = [{
        "type": "button",
        "name": "Inga tider kunde hämtas",
        "icon": "mdi:information-outline"
      }] %}
    {% endif %}

    {{ ns.items | tojson }}
grid_options:
  columns: 14
  rows: auto


***AUTOMATIONS***

alias: "Lulebo Tvättstuga Heartbeat"
description: "Håller sessionen mot Lulebo vid liv och uppdaterar vid omstart."
mode: single
trigger:
  - platform: homeassistant
    event: start
  - platform: time_pattern
    hours: "/4"
action:
  - service: homeassistant.update_entity
    target:
      entity_id: sensor.lulebo_laundry_availability







alias: Execute Laundry Booking
sequence:
  - service: lulebo_laundry.book
    data:
      date: "{{ booking_date }}"
      slot: "{{ booking_slot }}"
      
  # Lägger till tiden i Todo-listan
  - service: todo.add_item
    target:
      entity_id: todo.tvattstuga
    data:
      item: "Tvättid: {{ booking_date }}"
      description: "Bokad via Home Assistant"

  - delay: "00:00:04"
  - service: homeassistant.update_entity
    target:
      entity_id: sensor.lulebo_laundry_availability
  - service: notify.notify
    data:
      title: "Tvättstuga Bokad 🧺"
      message: "Tiden den {{ booking_date }} bokades framgångsrikt!"
mode: single





alias: Execute Laundry Cancellation
sequence:
  - service: lulebo_laundry.cancel
    data:
      date: "{{ target_date }}"
      
  # Tar automatiskt bort rätt rad från Todo-listan
  - service: todo.remove_item
    target:
      entity_id: todo.tvattstuga
    data:
      item: "Tvättid: {{ target_date }}"

  - delay: "00:00:04"
  - service: homeassistant.update_entity
    target:
      entity_id: sensor.lulebo_laundry_availability
  - service: notify.notify
    data:
      title: "Tvättstuga Avbokad ❌"
      message: "Tiden den {{ target_date }} har nu avbokats."
mode: single





