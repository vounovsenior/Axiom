import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { io } from 'socket.io-client';

// --- СТИЛИ (прям тут, чтобы не париться с CSS) ---
const styles = {
  container: {
    maxWidth: '1200px',
    margin: '0 auto',
    padding: '20px',
    fontFamily: 'Arial, sans-serif',
    backgroundColor: '#0d1117',
    color: '#e6edf3',
    minHeight: '100vh'
  },
  header: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    borderBottom: '1px solid #30363d',
    paddingBottom: '10px',
    marginBottom: '20px'
  },
  logo: {
    fontSize: '28px',
    fontWeight: 'bold',
    background: 'linear-gradient(45deg, #58a6ff, #f0883e)',
    WebkitBackgroundClip: 'text',
    WebkitTextFillColor: 'transparent'
  },
  card: {
    backgroundColor: '#161b22',
    border: '1px solid #30363d',
    borderRadius: '8px',
    padding: '20px',
    marginBottom: '20px'
  },
  input: {
    backgroundColor: '#0d1117',
    border: '1px solid #30363d',
    color: '#e6edf3',
    padding: '8px 12px',
    borderRadius: '4px',
    marginRight: '10px',
    marginBottom: '10px',
    width: '200px'
  },
  button: {
    backgroundColor: '#238636',
    color: 'white',
    border: 'none',
    padding: '8px 16px',
    borderRadius: '4px',
    cursor: 'pointer',
    marginRight: '10px'
  },
  buttonDanger: {
    backgroundColor: '#da3633',
    color: 'white',
    border: 'none',
    padding: '8px 16px',
    borderRadius: '4px',
    cursor: 'pointer'
  },
  grid: {
    display: 'grid',
    gridTemplateColumns: '1fr 1fr',
    gap: '20px'
  },
  table: {
    width: '100%',
    borderCollapse: 'collapse'
  },
  th: {
    textAlign: 'left',
    padding: '8px',
    borderBottom: '1px solid #30363d'
  },
  td: {
    padding: '8px',
    borderBottom: '1px solid #21262d'
  },
  buy: { color: '#3fb950' },
  sell: { color: '#f85149' }
};

// --- ОСНОВНОЙ КОМПОНЕНТ ---
function App() {
  const [token, setToken] = useState(localStorage.getItem('token') || '');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [balance, setBalance] = useState(null);
  const [walletAddress, setWalletAddress] = useState('');
  const [orders, setOrders] = useState([]);
  const [orderbook, setOrderbook] = useState({ bids: [], asks: [] });
  const [price, setPrice] = useState('');
  const [amount, setAmount] = useState('');
  const [side, setSide] = useState('buy');
  const [message, setMessage] = useState('');

  // --- ПОДКЛЮЧЕНИЕ К WEBSOCKET ---
  useEffect(() => {
    if (!token) return;

    const socket = io('http://localhost:8000', {
      transports: ['websocket'],
      auth: { token }
    });

    socket.on('connect', () => {
      console.log('✅ WebSocket connected');
      socket.emit('subscribe_orderbook', 'TON/USDT');
    });

    socket.on('orderbook_update', (data) => {
      setOrderbook(data);
    });

    socket.on('trade_executed', (data) => {
      setMessage(`✅ Сделка исполнена: ${data.amount} TON по ${data.price} USDT`);
      fetchBalance();
      fetchOrders();
    });

    return () => socket.disconnect();
  }, [token]);

  // --- ФУНКЦИИ ДЛЯ API ---

  const api = axios.create({
    baseURL: 'http://localhost:8000',
    headers: token ? { Authorization: `Bearer ${token}` } : {}
  });

  const register = async () => {
    try {
      const res = await api.post('/auth/register', { email, password });
      setMessage(`✅ Зарегистрирован: ${res.data.email}`);
    } catch (e) {
      setMessage(`❌ Ошибка: ${e.response?.data?.detail || e.message}`);
    }
  };

  const login = async () => {
    try {
      const res = await api.post('/auth/login', { email, password });
      setToken(res.data.access_token);
      localStorage.setItem('token', res.data.access_token);
      setMessage('✅ Вход выполнен');
      await fetchBalance();
      await fetchOrders();
      await fetchOrderbook();
    } catch (e) {
      setMessage(`❌ Ошибка: ${e.response?.data?.detail || e.message}`);
    }
  };

  const createWallet = async () => {
    try {
      const res = await api.post('/wallet/create');
      setWalletAddress(res.data.address);
      setMessage(`✅ Кошелёк создан: ${res.data.address}`);
      await fetchBalance();
    } catch (e) {
      setMessage(`❌ Ошибка: ${e.response?.data?.detail || e.message}`);
    }
  };

  const fetchBalance = async () => {
    try {
      const res = await api.get('/wallet/balance');
      setBalance(res.data);
    } catch (e) {
      console.error('Balance error', e);
    }
  };

  const fetchOrders = async () => {
    try {
      const res = await api.get('/trading/orders');
      setOrders(res.data);
    } catch (e) {
      console.error('Orders error', e);
    }
  };

  const fetchOrderbook = async () => {
    try {
      const res = await api.get('/trading/orderbook?pair=TON/USDT');
      setOrderbook(res.data);
    } catch (e) {
      console.error('Orderbook error', e);
    }
  };

  const createOrder = async () => {
    try {
      await api.post('/trading/order', {
        pair: 'TON/USDT',
        side,
        price: parseFloat(price),
        amount: parseFloat(amount)
      });
      setMessage('✅ Ордер создан');
      await fetchOrders();
      await fetchOrderbook();
    } catch (e) {
      setMessage(`❌ Ошибка: ${e.response?.data?.detail || e.message}`);
    }
  };

  const withdraw = async (address, amount) => {
    try {
      await api.post('/wallet/withdraw', { address, amount: parseFloat(amount) });
      setMessage('✅ Вывод выполнен');
      await fetchBalance();
    } catch (e) {
      setMessage(`❌ Ошибка: ${e.response?.data?.detail || e.message}`);
    }
  };

  // --- ОТРИСОВКА ---

  if (!token) {
    return (
      <div style={styles.container}>
        <div style={styles.header}>
          <div style={styles.logo}>⚡ AXIOM</div>
        </div>
        <div style={styles.card}>
          <h2>Вход в Axiom Exchange</h2>
          <input
            style={styles.input}
            placeholder="Email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
          <input
            style={styles.input}
            placeholder="Пароль"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          <button style={styles.button} onClick={login}>Войти</button>
          <button style={styles.button} onClick={register}>Регистрация</button>
          {message && <p>{message}</p>}
        </div>
      </div>
    );
  }

  return (
    <div style={styles.container}>
      {/* HEADER */}
      <div style={styles.header}>
        <div style={styles.logo}>⚡ AXIOM</div>
        <div>
          <span style={{ marginRight: '20px' }}>👤 {email}</span>
          <button style={styles.buttonDanger} onClick={() => {
            localStorage.removeItem('token');
            setToken('');
          }}>Выйти</button>
        </div>
      </div>

      {/* СООБЩЕНИЯ */}
      {message && (
        <div style={{ ...styles.card, backgroundColor: '#1c2333' }}>
          {message}
        </div>
      )}

      {/* БАЛАНС И КОШЕЛЁК */}
      <div style={styles.grid}>
        <div style={styles.card}>
          <h3>💰 Баланс</h3>
          {balance ? (
            <div>
              <p>TON: {balance.ton || 0}</p>
              <p>USDT: {balance.usdt || 0}</p>
            </div>
          ) : (
            <p>Загрузка...</p>
          )}
          <button style={styles.button} onClick={createWallet}>
            Создать кошелёк
          </button>
          {walletAddress && (
            <p style={{ fontSize: '12px', wordBreak: 'break-all' }}>
              Адрес: {walletAddress}
            </p>
          )}
          <div style={{ marginTop: '10px' }}>
            <input style={styles.input} placeholder="Адрес для вывода" id="withdrawAddr" />
            <input style={styles.input} placeholder="Количество" id="withdrawAmount" />
            <button style={styles.buttonDanger} onClick={() => {
              const addr = document.getElementById('withdrawAddr').value;
              const amt = document.getElementById('withdrawAmount').value;
              if (addr && amt) withdraw(addr, amt);
            }}>Вывести</button>
          </div>
        </div>

        {/* СОЗДАНИЕ ОРДЕРА */}
        <div style={styles.card}>
          <h3>📈 Создать ордер</h3>
          <select style={styles.input} value={side} onChange={(e) => setSide(e.target.value)}>
            <option value="buy">Покупка</option>
            <option value="sell">Продажа</option>
          </select>
          <input
            style={styles.input}
            placeholder="Цена (USDT)"
            value={price}
            onChange={(e) => setPrice(e.target.value)}
          />
          <input
            style={styles.input}
            placeholder="Количество (TON)"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
          />
          <button style={side === 'buy' ? styles.button : styles.buttonDanger} onClick={createOrder}>
            {side === 'buy' ? 'Купить' : 'Продать'}
          </button>
        </div>
      </div>

      {/* СТАКАН */}
      <div style={styles.card}>
        <h3>📊 Стакан (TON/USDT)</h3>
        <div style={styles.grid}>
          <div>
            <h4 style={styles.buy}>Покупка</h4>
            <table style={styles.table}>
              <thead><tr><th style={styles.th}>Цена</th><th style={styles.th}>Объём</th></tr></thead>
              <tbody>
                {(orderbook.bids || []).slice(0, 10).map((bid, i) => (
                  <tr key={i}><td style={styles.td}>{bid[0]}</td><td style={styles.td}>{bid[1]}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
          <div>
            <h4 style={styles.sell}>Продажа</h4>
            <table style={styles.table}>
              <thead><tr><th style={styles.th}>Цена</th><th style={styles.th}>Объём</th></tr></thead>
              <tbody>
                {(orderbook.asks || []).slice(0, 10).map((ask, i) => (
                  <tr key={i}><td style={styles.td}>{ask[0]}</td><td style={styles.td}>{ask[1]}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* МОИ ОРДЕРА */}
      <div style={styles.card}>
        <h3>📋 Мои ордера</h3>
        <table style={styles.table}>
          <thead><tr>
            <th style={styles.th}>Тип</th>
            <th style={styles.th}>Цена</th>
            <th style={styles.th}>Количество</th>
            <th style={styles.th}>Статус</th>
          </tr></thead>
          <tbody>
            {orders.map((order, i) => (
              <tr key={i}>
                <td style={styles.td} className={order.side === 'buy' ? styles.buy : styles.sell}>
                  {order.side === 'buy' ? '📈 Покупка' : '📉 Продажа'}
                </td>
                <td style={styles.td}>{order.price}</td>
                <td style={styles.td}>{order.amount}</td>
                <td style={styles.td}>{order.status || 'active'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default App;
