import { Link } from 'react-router';
import { ForecastCone } from '../components/art/ForecastCone.tsx';
import { Icon } from '../components/Icon.tsx';
import { brands, mark } from '../lib/assets.ts';

export default function HowItWorks() {
  return (
    <main>
      <title>How it works · Harbor</title>

      <section className="container split-hero">
        <div data-reveal>
          <h1>
            Forecasts in. <span className="muted">A plan you can afford out.</span>
          </h1>
          <p className="lead">
            Harbor joins the storm forecast, your accounts and the roads into one decision: when to leave, how to pay
            and where to go.
          </p>
          <div className="hero-actions">
            <Link className="button" to="/app">
              See a plan
              <Icon name="arrow" />
            </Link>
          </div>
        </div>
        <div className="stage orbit-stage" data-reveal style={{ '--d': '.1s' }}>
          <img
            className="stage-photo"
            src="https://images.unsplash.com/photo-1505228395891-9a51e7e86bf6?auto=format&fit=crop&w=1400&q=80"
            alt=""
          />
          <div className="orbit" role="img" aria-label="Harbor connects banks, forecasts, fuel, shelters and transit">
            <span className="ring r3" />
            <span className="ring r2" />
            <span className="core">
              <img src={mark} alt="" />
            </span>
            <span className="node" style={{ '--x': '0%', '--y': '-44%' }}>
              <img src={brands.chase} alt="" />
            </span>
            <span className="node" style={{ '--x': '31.1%', '--y': '-31.1%' }}>
              <img src={brands.bankofamerica} alt="" />
            </span>
            <span className="node" style={{ '--x': '44%', '--y': '0%' }}>
              <img src={brands.wellsfargo} alt="" />
            </span>
            <span className="node" style={{ '--x': '31.1%', '--y': '31.1%' }}>
              <img src={brands.robinhood} alt="" />
            </span>
            <span className="node" style={{ '--x': '0%', '--y': '44%' }}>
              <img src={brands.paypal} alt="" />
            </span>
            <span className="node" style={{ '--x': '-31.1%', '--y': '31.1%' }}>
              <img src={brands.venmo} alt="" />
            </span>
            <span className="node" style={{ '--x': '-44%', '--y': '0%' }}>
              <img src={brands.cashapp} alt="" />
            </span>
            <span className="node" style={{ '--x': '-31.1%', '--y': '-31.1%' }}>
              <img src={brands.zelle} alt="" />
            </span>
            <span className="node sm" style={{ '--x': '18.4%', '--y': '-18.4%' }}>
              <Icon name="rain" />
            </span>
            <span className="node sm" style={{ '--x': '18.4%', '--y': '18.4%' }}>
              <Icon name="fuel" />
            </span>
            <span className="node sm" style={{ '--x': '-18.4%', '--y': '18.4%' }}>
              <Icon name="tent" />
            </span>
            <span className="node sm" style={{ '--x': '-18.4%', '--y': '-18.4%' }}>
              <Icon name="bus" />
            </span>
          </div>
        </div>
      </section>

      <section className="section container">
        <div className="section-intro" data-reveal>
          <h2 className="title" style={{ marginTop: '10px' }}>
            Predictions on one side. <span className="muted">Decisions on the other.</span>
          </h2>
        </div>
        <div data-reveal>
          <div className="graph">
            <div className="col">
              <div className="gnode">
                <span className="ic">
                  <Icon name="tornado" />
                </span>
                <span>Storm forecast</span>
                <span className="tagline">NOAA</span>
              </div>
              <div className="gnode">
                <span className="ic">
                  <Icon name="pin" />
                </span>
                <span>Your address</span>
                <span className="tagline">You</span>
              </div>
              <div className="gnode">
                <span className="ic">
                  <img src={brands.chase} alt="" />
                </span>
                <span>Your accounts</span>
                <span className="tagline">Bank</span>
              </div>
              <div className="gnode">
                <span className="ic">
                  <Icon name="traffic" />
                </span>
                <span>Roads and fuel</span>
                <span className="tagline">Live</span>
              </div>
            </div>
            <svg className="wires" viewBox="0 0 100 400" preserveAspectRatio="none" aria-hidden="true">
              <path d="M0 50 C60 50 40 200 100 200" vectorEffect="non-scaling-stroke" />
              <path className="flow" d="M0 50 C60 50 40 200 100 200" vectorEffect="non-scaling-stroke" />
              <path d="M0 150 C60 150 40 200 100 200" vectorEffect="non-scaling-stroke" />
              <path className="flow" d="M0 150 C60 150 40 200 100 200" vectorEffect="non-scaling-stroke" />
              <path d="M0 250 C60 250 40 200 100 200" vectorEffect="non-scaling-stroke" />
              <path className="flow" d="M0 250 C60 250 40 200 100 200" vectorEffect="non-scaling-stroke" />
              <path d="M0 350 C60 350 40 200 100 200" vectorEffect="non-scaling-stroke" />
              <path className="flow" d="M0 350 C60 350 40 200 100 200" vectorEffect="non-scaling-stroke" />
            </svg>
            <div className="hub">
              <img src={mark} alt="" />
              <div>
                <b>Harbor</b>
                <br />
              </div>
            </div>
            <svg className="wires right" viewBox="0 0 100 400" preserveAspectRatio="none" aria-hidden="true">
              <path d="M0 200 C60 200 40 50 100 50" vectorEffect="non-scaling-stroke" />
              <path className="flow" d="M0 200 C60 200 40 50 100 50" vectorEffect="non-scaling-stroke" />
              <path d="M0 200 C60 200 40 150 100 150" vectorEffect="non-scaling-stroke" />
              <path className="flow" d="M0 200 C60 200 40 150 100 150" vectorEffect="non-scaling-stroke" />
              <path d="M0 200 C60 200 40 250 100 250" vectorEffect="non-scaling-stroke" />
              <path className="flow" d="M0 200 C60 200 40 250 100 250" vectorEffect="non-scaling-stroke" />
              <path d="M0 200 C60 200 40 350 100 350" vectorEffect="non-scaling-stroke" />
              <path className="flow" d="M0 200 C60 200 40 350 100 350" vectorEffect="non-scaling-stroke" />
            </svg>
            <div className="col">
              <div className="gnode out">
                <span className="ic">
                  <Icon name="clock" />
                </span>
                <span>Leave-by time</span>
              </div>
              <div className="gnode out">
                <span className="ic">
                  <Icon name="wallet" />
                </span>
                <span>Funded plan</span>
              </div>
              <div className="gnode out">
                <span className="ic">
                  <Icon name="route" />
                </span>
                <span>Route and fuel stop</span>
              </div>
              <div className="gnode out">
                <span className="ic">
                  <Icon name="tent" />
                </span>
                <span>A place to stay</span>
              </div>
            </div>
          </div>
          <div className="graph-legend">
            <span>
              <i />
              Signals in
            </span>
            <span className="o">
              <i />
              Decisions out
            </span>
          </div>
        </div>
      </section>

      <section className="section container">
        <div className="section-intro" data-reveal>
          <h2 className="title" style={{ marginTop: '10px' }}>
            Four steps, five days ahead.
          </h2>
        </div>
        <div className="features">
          <article className="feature step-card" data-reveal>
            <div className="feature-text">
              <h3>Predict</h3>
              <p>We watch the forecast cone and flag your address the day it falls inside.</p>
            </div>
            <div className="stage">
              <img
                className="stage-photo"
                src="https://images.unsplash.com/photo-1506905925346-21bda4d32df4?auto=format&fit=crop&w=1400&q=80"
                alt=""
              />
              <div className="viz">
                <h4>Forecast cone</h4>
                <ForecastCone />
              </div>
            </div>
          </article>
          <article className="feature flip step-card" data-reveal>
            <div className="feature-text">
              <h3>Connect</h3>
              <p>Harbor moves money out of stocks, savings and apps into one evacuation fund.</p>
            </div>
            <div className="stage">
              <img
                className="stage-photo"
                src="https://images.unsplash.com/photo-1473116763249-2faaef81ccda?auto=format&fit=crop&w=1400&q=80"
                alt=""
              />
              <div className="viz">
                <h4>Your evacuation fund</h4>
                <div className="accounts">
                  {[
                    [brands.robinhood, 'Stocks', 'Sold Monday', '+$500'],
                    [brands.chase, 'Savings', 'Moved today', '+$500'],
                    [brands.paypal, 'PayPal balance', 'Moved today', '+$200'],
                  ].map(([logo, name, when, amount]) => (
                    <div key={name} className="account">
                      <span className="account-logo">
                        <img src={logo} alt="" />
                      </span>
                      <span className="account-name">
                        {name}
                        <small>{when}</small>
                      </span>
                      <strong>{amount}</strong>
                    </div>
                  ))}
                  <div className="fund-total">
                    <span>
                      Evacuation fund
                      <small>Spend it on anything</small>
                    </span>
                    <strong>$1,200</strong>
                  </div>
                </div>
              </div>
            </div>
          </article>
          <article className="feature step-card" data-reveal>
            <div className="feature-text">
              <h3>Plan</h3>
              <p>Harbor prices the trip for your household, then you approve it in one tap.</p>
            </div>
            <div className="stage">
              <img
                className="stage-photo"
                src="https://images.unsplash.com/photo-1500375592092-40eb2168fd21?auto=format&fit=crop&w=1400&q=80"
                alt=""
              />
              <div className="viz">
                <h4>Where the money goes</h4>
                <div className="donut-wrap">
                  <svg viewBox="0 0 180 180" aria-label="Cost split: lodging $780, food $260, fuel $160">
                    <g transform="rotate(-90 90 90)" fill="none" strokeWidth="22">
                      <circle cx="90" cy="90" r="70" stroke="#eef0ec" />
                      <circle cx="90" cy="90" r="70" stroke="#19241f" strokeDasharray="285.9 439.8" />
                      <circle
                        cx="90"
                        cy="90"
                        r="70"
                        stroke="#ed6a3c"
                        strokeDasharray="95.4 439.8"
                        strokeDashoffset="-285.9"
                      />
                      <circle
                        cx="90"
                        cy="90"
                        r="70"
                        stroke="#1f7a93"
                        strokeDasharray="58.6 439.8"
                        strokeDashoffset="-381.3"
                      />
                    </g>
                    <text x="90" y="88" textAnchor="middle" fontFamily="Space Grotesk" fontSize="26" fill="#19241f">
                      $1,200
                    </text>
                    <text x="90" y="108" textAnchor="middle" fontFamily="Inter" fontSize="11" fill="#647169">
                      total
                    </text>
                  </svg>
                  <ul>
                    <li>
                      <i style={{ background: '#19241f' }} />
                      Lodging<b>$780</b>
                    </li>
                    <li>
                      <i style={{ background: '#ed6a3c' }} />
                      Food and essentials<b>$260</b>
                    </li>
                    <li>
                      <i style={{ background: '#1f7a93' }} />
                      Fuel and tolls<b>$160</b>
                    </li>
                  </ul>
                </div>
              </div>
            </div>
          </article>
          <article className="feature flip step-card" data-reveal>
            <div className="feature-text">
              <h3>Go</h3>
              <p>Leave ahead of the rush. Funds return after the storm.</p>
            </div>
            <div className="stage">
              <img
                className="stage-photo"
                src="https://images.unsplash.com/photo-1439405326854-014607f694d7?auto=format&fit=crop&w=1400&q=80"
                alt=""
              />
              <div className="viz">
                <h4>Beat the traffic peak</h4>
                <svg
                  viewBox="0 0 520 230"
                  aria-label="Traffic rises sharply after the warning; Harbor's leave-by time is before it"
                >
                  <g stroke="#eef0ec">
                    <line x1="40" y1="40" x2="500" y2="40" />
                    <line x1="40" y1="110" x2="500" y2="110" />
                    <line x1="40" y1="180" x2="500" y2="180" />
                  </g>
                  <path
                    d="M40 180 C90 179 132 177 178 174 S250 162 270 152 S300 125 316 112 S345 70 362 62 S395 44 408 46 S440 78 454 92 S485 160 500 172 L500 180 L40 180Z"
                    fill="#d64545"
                    fillOpacity=".1"
                  />
                  <path
                    d="M40 180 C90 179 132 177 178 174 S250 162 270 152 S300 125 316 112 S345 70 362 62 S395 44 408 46 S440 78 454 92 S485 160 500 172"
                    fill="none"
                    stroke="#d64545"
                    strokeWidth="2.5"
                  />
                  <line x1="293" y1="20" x2="293" y2="180" stroke="#ed6a3c" strokeWidth="2" strokeDasharray="5 4" />
                  <rect x="226" y="10" width="134" height="24" rx="12" fill="#ed6a3c" />
                  <text
                    x="293"
                    y="26"
                    textAnchor="middle"
                    fontFamily="Inter"
                    fontSize="11"
                    fontWeight="600"
                    fill="#fff"
                  >
                    Harbor: leave by 54h
                  </text>
                  <line x1="362" y1="50" x2="362" y2="180" stroke="#8f9a93" strokeDasharray="3 4" />
                  <text x="368" y="198" fontFamily="Inter" fontSize="11" fill="#647169">
                    Warning 36h
                  </text>
                  <g fontFamily="Inter" fontSize="11" fill="#8f9a93">
                    <text x="40" y="218">
                      120h
                    </text>
                    <text x="224" y="218">
                      72h
                    </text>
                    <text x="408" y="218">
                      24h
                    </text>
                    <text x="486" y="218">
                      0h
                    </text>
                  </g>
                  <circle cx="293" cy="140" r="6" fill="#ed6a3c" stroke="#fff" strokeWidth="2" />
                </svg>
              </div>
            </div>
          </article>
        </div>
      </section>
      <section className="closing container" style={{ marginTop: '104px' }} data-reveal>
        <img
          className="stage-photo"
          src="https://images.unsplash.com/photo-1476514525535-07fb3b4ae5f1?auto=format&fit=crop&w=2200&q=80"
          alt=""
        />
        <div className="closing-inner">
          <h2>
            Five days of warning. <em>One plan.</em>
          </h2>
          <div className="hero-actions" style={{ justifyContent: 'center' }}>
            <Link className="button" to="/app">
              See a plan
              <Icon name="arrow" />
            </Link>
          </div>
        </div>
      </section>
    </main>
  );
}
