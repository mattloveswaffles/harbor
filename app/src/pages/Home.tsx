import { Link } from 'react-router';
import { AddressForm } from '../components/AddressForm.tsx';
import { Icon } from '../components/Icon.tsx';
import { brands, dudes, mark, shorePhoto } from '../lib/assets.ts';

export default function Home() {
  return (
    <main>
      <section className="hero container" data-reveal>
        <h1>
          Harbor turns a hurricane warning into a plan to leave,{' '}
          <span className="muted">and makes sure you can pay for it.</span>
        </h1>
        <div className="hero-actions">
          <AddressForm cta="Get my plan" />
          <Link className="button light" to="/how-it-works">
            See how it works
            <Icon name="arrow" />
          </Link>
        </div>
      </section>

      <section className="container">
        <div className="stage hero-stage" data-reveal>
          <img className="stage-photo" src={shorePhoto} alt="" />
          <div
            className="app"
            role="img"
            aria-label="The Harbor app: the evacuation plan in three steps, before the storm"
          >
            <aside className="app-side">
              <span className="brand">
                <img src={mark} alt="" />
                harbor
              </span>
              <span className="side-item active">
                <Icon name="shield" />
                My plan
              </span>
              <span className="side-item">
                <Icon name="rain" />
                Weather
              </span>
              <span className="side-item">
                <Icon name="bank" />
                Accounts
              </span>
              <span className="side-item">
                <Icon name="route" />
                Route
              </span>
              <span className="side-item">
                <Icon name="tent" />
                Shelters
              </span>
              <span className="side-item">
                <Icon name="harbor" />
                Ask Harbor
              </span>
              <span className="side-user">
                <svg className="av-blob" aria-hidden="true" viewBox="0 0 100 100" width="34" height="34">
                  <g fill="#f6a27c">
                    <path d="M87.5 50.72C87.5 70.84 71.91 86.14 51.41 86.14C30.9 86.14 15.31 70.84 15.31 50.72C15.31 30.59 30.9 15.29 51.41 15.29C71.91 15.29 87.5 30.59 87.5 50.72Z" />
                  </g>
                  <g fill="#1b1310">
                    <path d="M40.39 48.22C39.22 56.21 39.22 56.21 35.64 55.68C32.06 55.16 32.06 55.16 33.23 47.17C34.39 39.18 34.39 39.18 37.97 39.7C41.55 40.23 41.55 40.23 40.39 48.22Z" />
                    <path d="M63.42 47.08C61.99 54.16 61.99 54.16 58.35 53.42C54.72 52.68 54.72 52.68 56.15 45.61C57.59 38.53 57.59 38.53 61.22 39.26C64.86 40 64.86 40 63.42 47.08Z" />
                  </g>
                </svg>
                <span>
                  Maria Lopez<small>Tampa, FL</small>
                </span>
              </span>
            </aside>
            <div className="app-main">
              <div className="mock-top">
                <b>My plan</b>
                <span className="mock-ask">
                  <Icon name="harbor" />
                  Ask Harbor anything…
                </span>
                <span className="mock-gear">
                  <Icon name="settings" />
                </span>
              </div>
              <div className="mock-banner">
                <img className="mock-dude" src={dudes.squall} alt="" />
                <span className="grow">
                  <strong>Leave by Tue 8:07 AM</strong>
                  <small>Milton · 68% chance of storm winds at home</small>
                </span>
                <span className="button small">
                  Approve $1,363
                  <Icon name="arrow" />
                </span>
              </div>
              <div className="mock-plan">
                <div className="mock-track">
                  <span>
                    <i>1</i>
                    <b />
                  </span>
                  <span>
                    <i>2</i>
                    <b />
                  </span>
                  <span>
                    <i>3</i>
                    <b />
                    <em>Storm winds Tue 11 PM</em>
                  </span>
                </div>
                <div className="mock-phases">
                  <div>
                    <small>Get ready</small>
                    <strong>Now</strong>
                    <p>$1,363 fund · Refill Lisinopril · Fill the tank</p>
                  </div>
                  <div>
                    <small>Leave</small>
                    <strong>Tue 8:07 AM</strong>
                    <p>I-75 N · 11h 53m in traffic</p>
                  </div>
                  <div>
                    <small>Arrive</small>
                    <strong>Macon, GA</strong>
                    <p>Around Tue 8 PM · backup shelter Middleton HS</p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="logos container" data-reveal>
        <p>Designed to connect to the accounts you already use</p>
        <div className="logo-tiles">
          <span className="logo-tile">
            <img src={brands.chase} alt="" />
            Chase
          </span>
          <span className="logo-tile">
            <img src={brands.bankofamerica} alt="" />
            Bank of America
          </span>
          <span className="logo-tile">
            <img src={brands.wellsfargo} alt="" />
            Wells Fargo
          </span>
          <span className="logo-tile">
            <img src={brands.robinhood} alt="" />
            Robinhood
          </span>
          <span className="logo-tile">
            <img src={brands.paypal} alt="" />
            PayPal
          </span>
          <span className="logo-tile">
            <img src={brands.venmo} alt="" />
            Venmo
          </span>
          <span className="logo-tile">
            <img src={brands.cashapp} alt="" />
            Cash App
          </span>
          <span className="logo-tile">
            <img src={brands.zelle} alt="" />
            Zelle
          </span>
        </div>
      </section>

      <section className="section container" id="product">
        <div className="section-intro" data-reveal>
          <h2 className="title">
            One plan. <span className="muted">Money, route and a place to stay.</span>
          </h2>
        </div>
        <div className="features">
          <article className="feature" data-reveal>
            <div className="feature-text">
              <span className="icon-badge">
                <Icon name="plug" />
              </span>
              <h3>Connect your bank in a click</h3>
              <p>Move money from stocks, savings and apps into one evacuation fund.</p>
            </div>
            <div className="stage">
              <img
                className="stage-photo"
                src="https://images.unsplash.com/photo-1505228395891-9a51e7e86bf6?auto=format&fit=crop&w=1400&q=80"
                alt=""
              />
              <div className="ui">
                <div className="ui-head">
                  <h4>Accounts</h4>
                </div>
                <div className="ui-body">
                  <div className="bank-grid">
                    <div className="bank">
                      <img src={brands.chase} alt="" />
                      <span>
                        <b>Chase</b>
                        <small className="on">Connected</small>
                      </span>
                    </div>
                    <div className="bank">
                      <img src={brands.bankofamerica} alt="" />
                      <span>
                        <b>Bank of America</b>
                        <small>Connect</small>
                      </span>
                    </div>
                    <div className="bank">
                      <img src={brands.wellsfargo} alt="" />
                      <span>
                        <b>Wells Fargo</b>
                        <small>Connect</small>
                      </span>
                    </div>
                    <div className="bank">
                      <img src={brands.robinhood} alt="" />
                      <span>
                        <b>Robinhood</b>
                        <small className="off">Optional</small>
                      </span>
                    </div>
                    <div className="bank">
                      <img src={brands.paypal} alt="" />
                      <span>
                        <b>PayPal</b>
                        <small>Connect</small>
                      </span>
                    </div>
                    <div className="bank">
                      <img src={brands.cashapp} alt="" />
                      <span>
                        <b>Cash App</b>
                        <small>Connect</small>
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </article>
          <article className="feature flip" data-reveal>
            <div className="feature-text">
              <span className="icon-badge">
                <Icon name="money" />
              </span>
              <h3>Funded before prices spike</h3>
              <p>The trip, priced and ready days ahead.</p>
            </div>
            <div className="stage">
              <img
                className="stage-photo"
                src="https://images.unsplash.com/photo-1473116763249-2faaef81ccda?auto=format&fit=crop&w=1400&q=80"
                alt=""
              />
              <div className="ui">
                <div className="ui-head">
                  <h4>Your plan</h4>
                </div>
                <div className="ui-body">
                  <div className="line-item">
                    <span className="ic">
                      <Icon name="fuel" />
                    </span>
                    <span>Fuel</span>
                    <b>$160</b>
                  </div>
                  <div className="line-item">
                    <span className="ic">
                      <Icon name="hotel" />
                    </span>
                    <span>Lodging</span>
                    <b>$780</b>
                  </div>
                  <div className="line-item">
                    <span className="ic">
                      <Icon name="heart" />
                    </span>
                    <span>Food</span>
                    <b>$260</b>
                  </div>
                  <div className="total">
                    <span>Total</span>
                    <strong>$1,200</strong>
                  </div>
                  <span className="button">
                    Approve plan
                    <Icon name="arrow" />
                  </span>
                </div>
              </div>
            </div>
          </article>
          <article className="feature" data-reveal>
            <div className="feature-text">
              <span className="icon-badge">
                <Icon name="route" />
              </span>
              <h3>A route around the gridlock</h3>
              <p>Leave before the rush, with a fuel stop and a room.</p>
            </div>
            <div className="stage">
              <img
                className="stage-photo"
                src="https://images.unsplash.com/photo-1506905925346-21bda4d32df4?auto=format&fit=crop&w=1400&q=80"
                alt=""
              />
              <div className="ui">
                <div className="ui-head">
                  <h4>Tampa → Lakeland</h4>
                </div>
                <div className="ui-body">
                  <svg className="mini-map" style={{ height: '220px' }} viewBox="0 0 520 220" aria-hidden="true">
                    <rect width="520" height="220" fill="#eef2ee" />
                    <path d="M0 100 C50 120 70 170 120 185 L120 220 L0 220Z" fill="#cfe1e8" />
                    <path
                      d="M0 60 L520 45 M100 0 L140 220 M260 0 L280 220 M390 0 L410 220"
                      stroke="#fff"
                      strokeWidth="7"
                    />
                    <path
                      d="M118 172 C200 140 260 130 330 95 S440 60 480 52"
                      stroke="#fff"
                      strokeWidth="10"
                      fill="none"
                    />
                    <path
                      d="M118 172 C200 140 240 133 280 118"
                      stroke="#d64545"
                      strokeWidth="5"
                      fill="none"
                      strokeLinecap="round"
                    />
                    <path
                      className="dash"
                      d="M118 172 C160 195 250 190 300 150 S420 70 480 52"
                      stroke="#ed6a3c"
                      strokeWidth="5"
                      fill="none"
                      strokeLinecap="round"
                    />
                    <circle cx="118" cy="172" r="8" fill="#19241f" stroke="#fff" strokeWidth="3" />
                    <circle cx="300" cy="150" r="7" fill="#fff" stroke="#19241f" strokeWidth="2.5" />
                    <circle cx="480" cy="52" r="8" fill="#ed6a3c" stroke="#fff" strokeWidth="3" />
                    <text x="132" y="200" fontFamily="Inter" fontSize="12" fill="#2a332d">
                      Tampa
                    </text>
                    <text x="312" y="170" fontFamily="Inter" fontSize="12" fill="#2a332d">
                      Fuel stop
                    </text>
                    <text x="410" y="40" fontFamily="Inter" fontSize="12" fill="#2a332d">
                      Lakeland
                    </text>
                  </svg>
                  <div className="legend">
                    <span>
                      <i style={{ background: '#ed6a3c' }} />
                      Your route
                    </span>
                    <span>
                      <i style={{ background: '#d64545' }} />
                      Congestion
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </article>
          <article className="feature flip" data-reveal>
            <div className="feature-text">
              <span className="icon-badge">
                <Icon name="bus" />
              </span>
              <h3>No car or no cash?</h3>
              <p>Free buses, pickup points and shelters.</p>
            </div>
            <div className="stage">
              <img
                className="stage-photo"
                src="https://images.unsplash.com/photo-1439405326854-014607f694d7?auto=format&fit=crop&w=1400&q=80"
                alt=""
              />
              <div className="ui">
                <div className="ui-head">
                  <h4>Free ride out</h4>
                </div>
                <div className="ui-body">
                  <div className="ride-steps">
                    <div className="ride">
                      <span className="ic">
                        <Icon name="pin" />
                      </span>
                      <span>Pickup point</span>
                      <b>Open</b>
                    </div>
                    <div className="ride">
                      <span className="ic">
                        <Icon name="bus" />
                      </span>
                      <span>Evacuation bus</span>
                      <b>Free</b>
                    </div>
                    <div className="ride">
                      <span className="ic">
                        <Icon name="tent" />
                      </span>
                      <span>Shelter</span>
                      <b>Space</b>
                    </div>
                    <div className="ride">
                      <span className="ic">
                        <Icon name="wheelchair" />
                      </span>
                      <span>Accessible pickup</span>
                      <b>Call</b>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </article>
        </div>
      </section>

      <section className="closing container" data-reveal>
        <img
          className="stage-photo"
          src="https://images.unsplash.com/photo-1476514525535-07fb3b4ae5f1?auto=format&fit=crop&w=2200&q=80"
          alt=""
        />
        <div className="closing-inner">
          <h2>
            See your way out <em>in 30 seconds.</em>
          </h2>
          <AddressForm cta="Get my plan" />
        </div>
      </section>
    </main>
  );
}
