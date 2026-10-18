// Settings popup: the household profile (GET/PUT /me/profile) and connected institutions (Nessie).
import { type ReactNode, useEffect, useState } from 'react';
import { AddressSearch } from '../../components/AddressSearch.tsx';
import { Icon, type IconName } from '../../components/Icon.tsx';
import { api } from '../../lib/api.ts';
import { brands } from '../../lib/assets.ts';
import { moneyRound } from '../../lib/format.ts';
import type { Connection, LatLon, Profile } from '../../lib/types.ts';
import { type SettingsTab, useDashboard } from './useHarbor.ts';

const TABS: [SettingsTab, string, IconName][] = [
  ['you', 'You', 'user'],
  ['places', 'Places', 'home'],
  ['household', 'Household', 'group'],
  ['medical', 'Medical', 'pill'],
  ['vehicle', 'Vehicle', 'car'],
  ['money', 'Money', 'wallet'],
  ['alerts', 'Alerts', 'alert'],
  ['privacy', 'Privacy', 'lock'],
];

type Edit = (change: (p: Profile) => void) => void;

function Field({
  label,
  value,
  onChange,
  type = 'text',
  wide,
}: {
  label: string;
  value: string | number | null;
  onChange: (v: string) => void;
  type?: string;
  wide?: boolean;
}) {
  return (
    <label className={wide ? 'field wide' : 'field'}>
      <span>{label}</span>
      <input type={type} value={value ?? ''} onChange={(e) => onChange(e.target.value)} />
    </label>
  );
}

function Toggle({
  label,
  sub,
  on,
  onChange,
}: {
  label: string;
  sub?: string;
  on: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <label className="setting">
      <span className="grow">
        <b>{label}</b>
        {sub && <small>{sub}</small>}
      </span>
      <input type="checkbox" className="switch" checked={on} onChange={(e) => onChange(e.target.checked)} />
    </label>
  );
}

function Seg<T extends string>({
  value,
  options,
  onChange,
}: {
  value: T;
  options: [T, string][];
  onChange: (v: T) => void;
}) {
  return (
    <span className="seg">
      {options.map(([v, label]) => (
        <button key={v} type="button" aria-pressed={v === value} onClick={() => onChange(v)}>
          {label}
        </button>
      ))}
    </span>
  );
}

/** Rows of small inputs with add and remove. `set` edits only this row's item. */
function Rows<T>({
  items,
  pick,
  edit,
  render,
  blank,
  add,
}: {
  items: T[];
  pick: (p: Profile) => T[];
  edit: Edit;
  render: (item: T, set: (change: (item: T) => void) => void) => ReactNode;
  blank: () => T;
  add: string;
}) {
  return (
    <>
      {items.map((item, i) => (
        // biome-ignore lint/suspicious/noArrayIndexKey: rows have no ids; order is the identity
        <div key={i} className="edit-row">
          {render(item, (change) =>
            edit((d) => {
              const x = pick(d)[i];
              if (x) change(x);
            }),
          )}
          <button
            className="icon-btn"
            type="button"
            aria-label="Remove"
            onClick={() =>
              edit((d) => {
                pick(d).splice(i, 1);
              })
            }
          >
            <Icon name="close" />
          </button>
        </div>
      ))}
      <button
        className="add"
        type="button"
        onClick={() =>
          edit((d) => {
            pick(d).push(blank());
          })
        }
      >
        <Icon name="plus" />
        {add}
      </button>
    </>
  );
}

const num = (v: string) => (v === '' ? null : Number(v));

function You({ p, edit }: { p: Profile; edit: Edit }) {
  return (
    <>
      <div className="grid2">
        <Field
          label="Full name"
          value={p.personal.name}
          onChange={(v) =>
            edit((d) => {
              d.personal.name = v;
            })
          }
        />
        <Field
          label="Date of birth"
          type="date"
          value={p.personal.dob}
          onChange={(v) =>
            edit((d) => {
              d.personal.dob = v;
            })
          }
        />
        <Field
          label="Mobile"
          type="tel"
          value={p.personal.phone}
          onChange={(v) =>
            edit((d) => {
              d.personal.phone = v;
            })
          }
        />
        <Field
          label="Email"
          type="email"
          value={p.personal.email}
          onChange={(v) =>
            edit((d) => {
              d.personal.email = v;
            })
          }
        />
      </div>
      <div className="line">
        <span className="grow">
          <b>Language</b>
          <small>For alerts and Ask Harbor</small>
        </span>
        <Seg
          value={p.personal.language}
          options={[
            ['en', 'English'],
            ['es', 'Español'],
          ]}
          onChange={(v) =>
            edit((d) => {
              d.personal.language = v;
            })
          }
        />
      </div>
      <h3>Emergency contacts</h3>
      <Rows
        items={p.contacts}
        add="Add contact"
        pick={(d) => d.contacts}
        edit={edit}
        blank={() => ({ name: '', relation: '', phone: '', gets_plan: true })}
        render={(c, set) => (
          <>
            <Field
              label="Name"
              value={c.name}
              onChange={(v) =>
                set((x) => {
                  x.name = v;
                })
              }
            />
            <Field
              label="Relation"
              value={c.relation}
              onChange={(v) =>
                set((x) => {
                  x.relation = v;
                })
              }
            />
            <Field
              label="Phone"
              type="tel"
              value={c.phone}
              onChange={(v) =>
                set((x) => {
                  x.phone = v;
                })
              }
            />
          </>
        )}
      />
    </>
  );
}

function Places({ p, edit, onMove }: { p: Profile; edit: Edit; onMove: (zip: string, at: LatLon) => void }) {
  return (
    <>
      <div className="field wide">
        <span>Home address</span>
        <AddressSearch
          cta="Set"
          initial={p.home.address}
          onPlace={(place) => {
            edit((d) => {
              d.home.address = place.label;
            });
            onMove(place.zip, { lat: place.lat, lon: place.lon });
          }}
          onText={(text) =>
            edit((d) => {
              d.home.address = text;
            })
          }
        />
      </div>
      <div className="line">
        <span className="grow">
          <b>Home type</b>
          <small>Mobile homes always evacuate</small>
        </span>
        <Seg
          value={p.home.home_type}
          options={[
            ['house', 'House'],
            ['apartment', 'Apartment'],
            ['mobile', 'Mobile home'],
          ]}
          onChange={(v) =>
            edit((d) => {
              d.home.home_type = v;
            })
          }
        />
      </div>
      <div className="line">
        <span className="grow">
          <b>Evacuation zone</b>
          <small>From your county's map</small>
        </span>
        <Seg
          value={p.home.evac_zone}
          options={[
            ['A', 'A'],
            ['B', 'B'],
            ['C', 'C'],
            ['D', 'D'],
            ['E', 'E'],
            ['none', 'None'],
            ['unsure', 'Not sure'],
          ]}
          onChange={(v) =>
            edit((d) => {
              d.home.evac_zone = v;
            })
          }
        />
      </div>
      <h3>Where you'd go and other places</h3>
      <Rows
        items={p.places}
        add="Add place"
        pick={(d) => d.places}
        edit={edit}
        blank={() => ({ label: '', address: '', kind: 'destination' })}
        render={(pl, set) => (
          <>
            <Field
              label="Name"
              value={pl.label}
              onChange={(v) =>
                set((x) => {
                  x.label = v;
                })
              }
            />
            <Field
              label="Address"
              value={pl.address}
              onChange={(v) =>
                set((x) => {
                  x.address = v;
                })
              }
            />
            <label className="field">
              <span>Kind</span>
              <select
                value={pl.kind}
                onChange={(e) =>
                  set((x) => {
                    x.kind = e.target.value as typeof pl.kind;
                  })
                }
              >
                <option value="destination">Where we'd go</option>
                <option value="school">School</option>
                <option value="work">Work</option>
                <option value="other">Other</option>
              </select>
            </label>
          </>
        )}
      />
    </>
  );
}

function Household({ p, edit }: { p: Profile; edit: Edit }) {
  return (
    <>
      <h3>People</h3>
      <Rows
        items={p.people}
        add="Add person"
        pick={(d) => d.people}
        edit={edit}
        blank={() => ({ name: '', age: null, relation: '' })}
        render={(pe, set) => (
          <>
            <Field
              label="Name"
              value={pe.name}
              onChange={(v) =>
                set((x) => {
                  x.name = v;
                })
              }
            />
            <Field
              label="Age"
              type="number"
              value={pe.age}
              onChange={(v) =>
                set((x) => {
                  x.age = num(v);
                })
              }
            />
            <Field
              label="Relation"
              value={pe.relation}
              onChange={(v) =>
                set((x) => {
                  x.relation = v;
                })
              }
            />
          </>
        )}
      />
      <h3>Pets</h3>
      <Rows
        items={p.pets}
        add="Add pet"
        pick={(d) => d.pets}
        edit={edit}
        blank={() => ({ name: '', type: 'dog', weight_lb: null, notes: '' })}
        render={(pet, set) => (
          <>
            <Field
              label="Name"
              value={pet.name}
              onChange={(v) =>
                set((x) => {
                  x.name = v;
                })
              }
            />
            <Field
              label="Kind"
              value={pet.type}
              onChange={(v) =>
                set((x) => {
                  x.type = v;
                })
              }
            />
            <Field
              label="Weight (lb)"
              type="number"
              value={pet.weight_lb}
              onChange={(v) =>
                set((x) => {
                  x.weight_lb = num(v);
                })
              }
            />
          </>
        )}
      />
    </>
  );
}

function Medical({ p, edit }: { p: Profile; edit: Edit }) {
  const m = p.medical;
  return (
    <>
      <h3>Medications</h3>
      <Rows
        items={m.medications}
        add="Add medication"
        pick={(d) => d.medical.medications}
        edit={edit}
        blank={() => ({ name: '', dose: '', person: '', schedule: '', days_left: null })}
        render={(med, set) => (
          <>
            <Field
              label="Medication"
              value={med.name}
              onChange={(v) =>
                set((x) => {
                  x.name = v;
                })
              }
            />
            <Field
              label="Dose"
              value={med.dose}
              onChange={(v) =>
                set((x) => {
                  x.dose = v;
                })
              }
            />
            <Field
              label="For"
              value={med.person}
              onChange={(v) =>
                set((x) => {
                  x.person = v;
                })
              }
            />
            <Field
              label="Days left"
              type="number"
              value={med.days_left}
              onChange={(v) =>
                set((x) => {
                  x.days_left = num(v);
                })
              }
            />
          </>
        )}
      />
      <h3>Needs</h3>
      <Toggle
        label="Equipment that needs power"
        sub="CPAP, oxygen concentrator, a powered wheelchair"
        on={m.needs_power}
        onChange={(v) =>
          edit((d) => {
            d.medical.needs_power = v;
          })
        }
      />
      <Toggle
        label="Home oxygen"
        on={m.oxygen}
        onChange={(v) =>
          edit((d) => {
            d.medical.oxygen = v;
          })
        }
      />
      <Toggle
        label="Dialysis"
        on={m.dialysis}
        onChange={(v) =>
          edit((d) => {
            d.medical.dialysis = v;
          })
        }
      />
      <Toggle
        label="Medicine that must stay cold"
        on={m.refrigerated_meds}
        onChange={(v) =>
          edit((d) => {
            d.medical.refrigerated_meds = v;
          })
        }
      />
      <div className="line">
        <span className="grow">
          <b>Mobility</b>
          <small>Shelters and rooms must be accessible</small>
        </span>
        <Seg
          value={m.mobility}
          options={[
            ['none', 'None'],
            ['walker', 'Walker'],
            ['wheelchair', 'Wheelchair'],
          ]}
          onChange={(v) =>
            edit((d) => {
              d.medical.mobility = v;
            })
          }
        />
      </div>
      <div className="grid2">
        <Field
          label="Equipment"
          value={m.equipment.join(', ')}
          onChange={(v) =>
            edit((d) => {
              d.medical.equipment = v
                .split(',')
                .map((s) => s.trim())
                .filter(Boolean);
            })
          }
        />
        <Field
          label="Allergies"
          value={m.allergies}
          onChange={(v) =>
            edit((d) => {
              d.medical.allergies = v;
            })
          }
        />
        <Field
          label="Pharmacy"
          value={m.pharmacy}
          onChange={(v) =>
            edit((d) => {
              d.medical.pharmacy = v;
            })
          }
          wide
        />
      </div>
    </>
  );
}

function Vehicle({ p, edit }: { p: Profile; edit: Edit }) {
  const v = p.vehicle;
  const range = v.has_car && v.mpg && v.tank_gal ? Math.round(v.mpg * v.tank_gal) : null;
  return (
    <>
      <Toggle
        label="We have a car"
        sub="Without one, Harbor plans rides and county buses"
        on={v.has_car}
        onChange={(x) =>
          edit((d) => {
            d.vehicle.has_car = x;
          })
        }
      />
      {v.has_car && (
        <>
          <div className="grid2">
            <Field
              label="Make and model"
              value={v.make_model}
              onChange={(x) =>
                edit((d) => {
                  d.vehicle.make_model = x;
                })
              }
            />
            <Field
              label="Seats"
              type="number"
              value={v.seats}
              onChange={(x) =>
                edit((d) => {
                  d.vehicle.seats = num(x);
                })
              }
            />
            <Field
              label="Miles per gallon"
              type="number"
              value={v.mpg}
              onChange={(x) =>
                edit((d) => {
                  d.vehicle.mpg = num(x);
                })
              }
            />
            <Field
              label="Tank size (gal)"
              type="number"
              value={v.tank_gal}
              onChange={(x) =>
                edit((d) => {
                  d.vehicle.tank_gal = num(x);
                })
              }
            />
          </div>
          <div className="line">
            <span className="grow">
              <b>Gas now</b>
              <small>{range ? `${Math.round(range * v.fuel_level)} of ${range} mi` : 'Add mpg and tank size'}</small>
            </span>
            <input
              className="range-input"
              type="range"
              min={0}
              max={1}
              step={0.125}
              value={v.fuel_level}
              onChange={(e) =>
                edit((d) => {
                  d.vehicle.fuel_level = Number(e.target.value);
                })
              }
              aria-label="Gas now"
            />
          </div>
          <Toggle
            label="Towing a trailer"
            sub="Cuts range by about a fifth"
            on={v.towing}
            onChange={(x) =>
              edit((d) => {
                d.vehicle.towing = x;
              })
            }
          />
        </>
      )}
    </>
  );
}

function Money({ connections }: { connections: Connection[] }) {
  const { act } = useDashboard();
  const [busy, setBusy] = useState<string | null>(null);
  const run = async (c: Connection) => {
    setBusy(c.id);
    await act(
      () => (c.connected ? api.disconnect(c.id) : api.connect(c.id)),
      c.connected ? `${c.name} disconnected.` : `${c.name} connected through Nessie.`,
    );
    setBusy(null);
  };
  return (
    <>
      <p className="hint">
        <Icon name="lock" />
        Accounts connect through Capital One's Nessie. Nothing moves until you approve a plan.
      </p>
      {connections.map((c) => (
        <div key={c.id} className="row">
          <span className="logo">
            <img src={brands[c.id as keyof typeof brands]} alt="" />
          </span>
          <span className="grow">
            <b>{c.name}</b>
            <small>
              {c.connected
                ? `${c.accounts.map((a) => a.nickname).join(', ')} · ${moneyRound(c.total_cents)}`
                : { bank: 'Checking and savings', brokerage: 'Investments', wallet: 'Balance' }[c.kind]}
            </small>
          </span>
          <button
            className={c.connected ? 'btn ghost small' : 'btn small'}
            type="button"
            disabled={busy === c.id}
            onClick={() => run(c)}
          >
            {busy === c.id ? '…' : c.connected ? 'Disconnect' : 'Connect'}
          </button>
        </div>
      ))}
    </>
  );
}

function Alerts({ p, edit }: { p: Profile; edit: Edit }) {
  const a = p.alerts;
  return (
    <>
      <Toggle
        label="Text messages"
        sub={p.personal.phone || 'Add a mobile number'}
        on={a.sms}
        onChange={(v) =>
          edit((d) => {
            d.alerts.sms = v;
          })
        }
      />
      <Toggle
        label="Email"
        sub={p.personal.email || 'Add an email'}
        on={a.email}
        onChange={(v) =>
          edit((d) => {
            d.alerts.email = v;
          })
        }
      />
      <Toggle
        label="Push notifications"
        sub="On this device"
        on={a.push}
        onChange={(v) =>
          edit((d) => {
            d.alerts.push = v;
          })
        }
      />
      <Toggle
        label="Quiet hours"
        sub="10 PM to 7 AM, except emergencies"
        on={a.quiet_hours}
        onChange={(v) =>
          edit((d) => {
            d.alerts.quiet_hours = v;
          })
        }
      />
      <Toggle
        label="Tell my contacts when we leave"
        sub="Shares the route and arrival time"
        on={a.tell_contacts}
        onChange={(v) =>
          edit((d) => {
            d.alerts.tell_contacts = v;
          })
        }
      />
    </>
  );
}

function Privacy({ p, edit }: { p: Profile; edit: Edit }) {
  return (
    <>
      <Toggle
        label="Share location while driving"
        sub="Updates the route in traffic"
        on={p.privacy.share_location}
        onChange={(v) =>
          edit((d) => {
            d.privacy.share_location = v;
          })
        }
      />
      <Toggle
        label="Use medical details only for planning"
        sub="Never shared with banks or shelters"
        on={p.privacy.medical_for_planning_only}
        onChange={(v) =>
          edit((d) => {
            d.privacy.medical_for_planning_only = v;
          })
        }
      />
    </>
  );
}

export function Settings({
  tab,
  onTab,
  onClose,
}: {
  tab: SettingsTab;
  onTab: (t: SettingsTab) => void;
  onClose: () => void;
}) {
  const { data, act } = useDashboard();
  const [draft, setDraft] = useState<Profile | null>(null);
  const [move, setMove] = useState<{ zip: string; location: LatLon } | null>(null);
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    api.profile().then(setDraft, () => undefined);
  }, []);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    addEventListener('keydown', onKey);
    return () => removeEventListener('keydown', onKey);
  }, [onClose]);

  const edit: Edit = (change) => {
    setDraft((p) => {
      if (!p) return p;
      const next = structuredClone(p);
      change(next);
      return next;
    });
    setDirty(true);
  };
  const save = async () => {
    if (!draft) return;
    await act(() => api.saveProfile({ ...draft, ...(move ?? {}) }), 'Saved. Harbor is updating your plan.');
    setDirty(false);
    setMove(null);
  };

  const panes: Record<SettingsTab, (p: Profile) => ReactNode> = {
    you: (p) => <You p={p} edit={edit} />,
    places: (p) => <Places p={p} edit={edit} onMove={(zip, location) => setMove({ zip, location })} />,
    household: (p) => <Household p={p} edit={edit} />,
    medical: (p) => <Medical p={p} edit={edit} />,
    vehicle: (p) => <Vehicle p={p} edit={edit} />,
    money: () => <Money connections={data.connections} />,
    alerts: (p) => <Alerts p={p} edit={edit} />,
    privacy: (p) => <Privacy p={p} edit={edit} />,
  };
  const title = TABS.find(([id]) => id === tab)?.[1];

  return (
    <div className="modal-back">
      <button className="modal-scrim" type="button" aria-label="Close settings" onClick={onClose} />
      <div className="modal" role="dialog" aria-modal="true" aria-label="Settings">
        <aside className="stabs">
          <b>Settings</b>
          {TABS.map(([id, label, icon]) => (
            <button key={id} type="button" aria-pressed={id === tab} onClick={() => onTab(id)}>
              <Icon name={icon} />
              {label}
            </button>
          ))}
        </aside>
        <section className="spane">
          <h2>{title}</h2>
          {draft ? panes[tab](draft) : <span className="spin" />}
          {tab !== 'money' && (
            <footer className="sfoot">
              <small>{dirty ? 'Unsaved changes' : 'Harbor plans with these details'}</small>
              <button className="btn" type="button" disabled={!dirty} onClick={save}>
                Save
              </button>
            </footer>
          )}
        </section>
        <button className="close" type="button" aria-label="Close" onClick={onClose}>
          <Icon name="close" />
        </button>
      </div>
    </div>
  );
}
