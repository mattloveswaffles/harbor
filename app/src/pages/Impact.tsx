import { Link } from 'react-router';
import { Icon } from '../components/Icon.tsx';
import { DOCS } from '../components/SiteLayout.tsx';
import { Waffle } from '../components/Waffle.tsx';

export default function Impact() {
  return (
    <main>
      <title>Impact · Harbor</title>

      <section className="container split-hero">
        <div data-reveal>
          <h1>
            More people out in time. <span className="muted">Fewer left behind.</span>
          </h1>
          <p className="lead">What Harbor could change for one household, one bank and the whole coast.</p>
          <div className="hero-actions">
            <Link className="button" to="/app">
              See a plan
              <Icon name="arrow" />
            </Link>
            <a className="button light" href={`${DOCS}/Harbor.pptx`}>
              Pitch deck
              <Icon name="arrow" />
            </a>
          </div>
        </div>
        <div className="stage" data-reveal style={{ '--d': '.1s' }}>
          <img
            className="stage-photo"
            src="https://images.unsplash.com/photo-1501785888041-af3ef285b470?auto=format&fit=crop&w=1400&q=80"
            alt=""
          />
          <div className="glass-card">
            <div className="rows" style={{ marginTop: '10px' }}>
              <div className="row">
                <Icon name="rain" />
                Warning received<b>Day 5</b>
              </div>
              <div className="row">
                <Icon name="shield" />
                Plan built<b>2 minutes</b>
              </div>
              <div className="row">
                <Icon name="wallet" />
                Cash ready<b>48h out</b>
              </div>
              <div className="row">
                <Icon name="car" />
                On the road<b>Before the warning</b>
              </div>
            </div>
            <div className="sum">
              <span>Trip covered</span>
              <strong>$1,200</strong>
            </div>
          </div>
        </div>
      </section>
      <section className="container" data-reveal>
        <div className="figures">
          <div>
            <strong>1M</strong>
            <span className="mono">People reached with one bank partner</span>
          </div>
          <div>
            <strong>130K</strong>
            <span className="mono">Of them without emergency cash today</span>
          </div>
          <div>
            <strong>7.8M</strong>
            <span className="mono">Coastwide, without emergency cash</span>
          </div>
        </div>
      </section>

      <section className="band">
        <div className="container chart-section">
          <div data-reveal>
            <h2>
              From the whole coast <span className="muted">to the people one bank can reach.</span>
            </h2>
            <p className="sub">
              Every year, millions are told to leave. One bank partner puts a plan in a million pockets.
            </p>
            <div className="key-list">
              <div>
                <i style={{ background: '#dfe3dd' }} />
                Coastal residents<b>60M</b>
              </div>
              <div>
                <i style={{ background: '#19241f' }} />
                Displaced each year<b>3.4M</b>
              </div>
              <div>
                <i style={{ background: 'var(--accent)' }} />
                One bank partner<b>1M</b>
              </div>
            </div>
          </div>
          <div className="stage" data-reveal style={{ '--d': '.1s' }}>
            <img
              className="stage-photo"
              src="https://images.unsplash.com/photo-1470770841072-f978cf4d019e?auto=format&fit=crop&w=1400&q=80"
              alt=""
            />
            <div className="viz">
              <h4>People in the path</h4>
              <small>Circle area to scale</small>
              <svg
                viewBox="0 0 420 380"
                aria-label="Nested circles: 60 million coastal residents, 3.4 million displaced each year, 1 million with one bank partner"
              >
                <circle cx="190" cy="190" r="180" fill="#f0f2ee" stroke="#dfe3dd" />
                <circle cx="190" cy="327" r="43" fill="#19241f" />
                <circle cx="190" cy="347" r="23" fill="#ed6a3c" />
                <text x="190" y="120" textAnchor="middle" fontFamily="Space Grotesk" fontSize="44" fill="#19241f">
                  60M
                </text>
                <text x="190" y="144" textAnchor="middle" fontFamily="Inter" fontSize="13" fill="#647169">
                  coastal residents
                </text>
                <line x1="228.9" y1="308.7" x2="328" y2="262" stroke="#19241f" strokeLinecap="round" />
                <circle cx="228.9" cy="308.7" r="2.5" fill="#19241f" />
                <text x="334" y="262" dominantBaseline="middle" fontFamily="Inter" fontSize="12" fill="#19241f">
                  3.4M displaced
                </text>
                <line x1="212.8" y1="344.2" x2="328" y2="330" stroke="#ed6a3c" strokeLinecap="round" />
                <circle cx="212.8" cy="344.2" r="2.5" fill="#ed6a3c" />
                <text
                  x="334"
                  y="330"
                  dominantBaseline="middle"
                  fontFamily="Inter"
                  fontSize="12"
                  fontWeight="600"
                  fill="#ed6a3c"
                >
                  1M reached
                </text>
              </svg>
              <div className="foot">
                <span>Harbor estimate · US Census</span>
                <b>Projection</b>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="section container chart-section flip">
        <div data-reveal>
          <h2>
            Out of every 100 people, <span className="muted">who can’t leave on their own.</span>
          </h2>
          <p className="sub">
            Of one bank’s million customers, Harbor could help about 130,000 pay for the trip, and 85,000 find a free
            ride.
          </p>
          <div className="key-list">
            <div>
              <i style={{ background: 'var(--accent)' }} />
              Helped to pay for the trip<b>130K</b>
            </div>
            <div>
              <i style={{ background: '#1f7a93' }} />
              Given a free ride out<b>85K</b>
            </div>
          </div>
        </div>
        <div className="stage" data-reveal style={{ '--d': '.1s' }}>
          <img
            className="stage-photo"
            src="https://images.unsplash.com/photo-1501785888041-af3ef285b470?auto=format&fit=crop&w=1400&q=80"
            alt=""
          />
          <div className="viz">
            <h4>Every dot is one person</h4>
            <small>Shares of U.S. adults and households</small>
            <div className="waffles">
              <div>
                <Waffle fill={13} />
                <div className="waffle-cap">
                  <strong>13%</strong>can’t cover a $400 emergency
                </div>
              </div>
              <div>
                <Waffle fill={8.5} className="teal" />
                <div className="waffle-cap teal">
                  <strong>8.5%</strong>live in a home with no car
                </div>
              </div>
            </div>
            <div className="foot">
              <span>Federal Reserve, 2024 · Census ACS, 2024</span>
              <b>Projection</b>
            </div>
          </div>
        </div>
      </section>

      <section className="section container chart-section">
        <div data-reveal>
          <h2>
            Each bank we add <span className="muted">gets more people out in time.</span>
          </h2>
          <p className="sub">
            People without emergency cash, helped each year, as bank partners join. Each partner ≈ 1M customers.
          </p>
          <div className="key-list">
            <div>
              <i style={{ background: 'var(--accent)' }} />
              Year 1 · 1 bank<b>130K</b>
            </div>
            <div>
              <i style={{ background: 'var(--accent)' }} />
              Year 5 · 12 banks<b>1.56M</b>
            </div>
          </div>
        </div>
        <div className="stage" data-reveal style={{ '--d': '.1s' }}>
          <img
            className="stage-photo"
            src="https://images.unsplash.com/photo-1507525428034-b723cf961d3e?auto=format&fit=crop&w=1400&q=80"
            alt=""
          />
          <div className="viz">
            <h4>People helped per year</h4>
            <small>Scenario: 1, 3, 5, 8, 12 bank partners</small>
            <div className="stat-row">
              <div>
                <small>Year 1</small>
                <strong>130K</strong>
              </div>
              <div>
                <small>Year 3</small>
                <strong>650K</strong>
              </div>
              <div className="hl">
                <small>Year 5</small>
                <strong>1.56M</strong>
              </div>
            </div>
            <svg viewBox="0 0 600 260" aria-label="Line rising from 130 thousand in year 1 to 1.56 million in year 5">
              <defs>
                <linearGradient id="lg" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0" stopColor="#ed6a3c" stopOpacity=".28" />
                  <stop offset="1" stopColor="#ed6a3c" stopOpacity="0" />
                </linearGradient>
              </defs>
              <g stroke="#eef0ec" strokeDasharray="2 4">
                <line x1="50" y1="30" x2="580" y2="30" />
                <line x1="50" y1="80" x2="580" y2="80" />
                <line x1="50" y1="130" x2="580" y2="130" />
                <line x1="50" y1="180" x2="580" y2="180" />
              </g>
              <line x1="50" y1="230" x2="580" y2="230" stroke="#dfe3dd" />
              <g fontFamily="ui-monospace,Menlo,Consolas,monospace" fontSize="11" fill="#8f9a93">
                <text x="8" y="34">
                  1.6M
                </text>
                <text x="8" y="134">
                  800K
                </text>
                <text x="22" y="234">
                  0
                </text>
              </g>
              <path
                d="M80 213.75 C140 205 150 190 200 181.25 S290 155 320 148.75 S400 112 440 100 S520 50 560 35 L560 230 L80 230Z"
                fill="url(#lg)"
              />
              <path
                d="M80 213.75 C140 205 150 190 200 181.25 S290 155 320 148.75 S400 112 440 100 S520 50 560 35"
                fill="none"
                stroke="#ed6a3c"
                strokeWidth="3"
              />
              <g fill="#fff" stroke="#ed6a3c" strokeWidth="2.5">
                <circle cx="80" cy="213.75" r="5" />
                <circle cx="200" cy="181.25" r="5" />
                <circle cx="320" cy="148.75" r="5" />
                <circle cx="440" cy="100" r="5" />
                <circle cx="560" cy="35" r="7" fill="#ed6a3c" />
              </g>
              <g fontFamily="ui-monospace,Menlo,Consolas,monospace" fontSize="11" fill="#8f9a93" textAnchor="middle">
                <text x="80" y="252">
                  Y1
                </text>
                <text x="200" y="252">
                  Y2
                </text>
                <text x="320" y="252">
                  Y3
                </text>
                <text x="440" y="252">
                  Y4
                </text>
                <text x="560" y="252">
                  Y5
                </text>
              </g>
            </svg>
            <div className="foot">
              <span>13% of customers × bank partners</span>
              <b>Scenario</b>
            </div>
          </div>
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
            A concept today. <em>A way out tomorrow.</em>
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
