import React, { useState, useEffect, useRef } from 'react';
import { Mic, Search, ShoppingBag, ArrowLeft, Package } from 'lucide-react';

const API_BASE = "http://localhost:8000";
const WS_BASE = "ws://localhost:8000";

// --- Helpers ---
function parseImage(urlStr) {
  if (!urlStr) return null;
  try {
    const arr = JSON.parse(urlStr);
    if (Array.isArray(arr) && arr.length > 0) return arr[0];
  } catch (e) {}
  
  if (typeof urlStr === 'string') {
    const parts = urlStr.split(',');
    if (parts.length > 0 && parts[0].trim().startsWith('http')) {
      return parts[0].trim();
    }
  }
  return null;
}

// --- Components ---

function Navbar({ cartCount, setView, onSearch }) {
  const [searchText, setSearchText] = useState("");

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && searchText.trim()) {
      onSearch(searchText.trim());
      setSearchText("");
    }
  };

  return (
    <nav className="navbar glass-nav">
      <div className="nav-brand" onClick={() => setView('home')}>
        <Package size={28} color="#8b5cf6" />
        AI-KART V2
      </div>
      <div className="nav-search">
        <Search size={18} color="#94a3b8" />
        <input 
          type="text" 
          placeholder="Ask ShopBot to find products..." 
          value={searchText}
          onChange={(e) => setSearchText(e.target.value)}
          onKeyDown={handleKeyDown}
        />
      </div>
      <div style={{display: 'flex', gap: '1rem'}}>
        <button className="btn-primary glass" style={{background: 'transparent'}} onClick={() => setView('cart')}>
          <ShoppingBag size={20} />
          Cart
          {cartCount > 0 && <span style={{background: '#ef4444', color: '#fff', borderRadius: '50%', padding: '2px 8px', fontSize: '0.8rem'}}>{cartCount}</span>}
        </button>
      </div>
    </nav>
  );
}

function ProductGrid({ products, selectedCategory, onSelectProduct, addToCart, searchResultsIds }) {
  const filteredProducts = products.filter(p => {
    if (selectedCategory === "Search Results" && searchResultsIds) return searchResultsIds.includes(p.id);
    if (selectedCategory === "All" || selectedCategory === "Search Results") return true;
    if (p.category_name && p.category_name.toLowerCase() === selectedCategory.toLowerCase()) return true;
    try {
      const tags = JSON.parse(p.tags || "[]");
      return tags.map(t => t.toLowerCase()).includes(selectedCategory.toLowerCase());
    } catch { return false; }
  });

  return (
    <div style={{paddingBottom: '100px'}}>
      <h2 style={{padding: '2rem 2rem 0', fontSize: '2rem', letterSpacing: '-0.5px'}}>
        {selectedCategory === "All" ? "Curated Collection" : `${selectedCategory}`}
      </h2>
      <div className="product-grid">
        {filteredProducts.map(p => {
          const imgUrl = parseImage(p.image_url);
          return (
            <div key={p.id} className="product-card glass" onClick={() => onSelectProduct(p)}>
              <img className="product-image" src={imgUrl || "https://placehold.co/400?text=No+Image"} alt={p.name} />
              <div className="product-brand">{p.brand || 'AI-KART Studio'}</div>
              <div className="product-name">{p.name}</div>
              <div className="product-price-row">
                <span className="price-current">₹{p.price.toFixed(2)}</span>
                {p.original_price > p.price && <span className="price-original">₹{p.original_price.toFixed(2)}</span>}
              </div>
              <button className="btn-primary" onClick={(e) => { e.stopPropagation(); addToCart(p); }}>
                Add to Cart
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function VoiceOrb({ onNavigate, onAddToCart, onUpdateCartQuantity, onRemoveFromCart, onClearCart, onFilterCategory, onSelectProductById, onShowProducts, products }) {
  const [state, setState] = useState('idle'); 
  const [message, setMessage] = useState('');
  const [conversationHistory, setConversationHistory] = useState([]);
  
  const ws = useRef(null);
  const mediaRecorder = useRef(null);
  const audioChunks = useRef([]);
  const audioObj = useRef(null);

  useEffect(() => {
    const connectWs = () => {
      ws.current = new WebSocket(`${WS_BASE}/ws/chat`);
      ws.current.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          handleServerEvent(data);
        } catch(e) { console.error("WS parse error", e); }
      };
      ws.current.onclose = () => setTimeout(connectWs, 3000);
    };
    connectWs();
    return () => { if(ws.current) ws.current.close(); };
  }, [products]); // Rebind when products update for ADD_TO_CART lookups

  const handleServerEvent = (data) => {
    if (data.event === "transcript") {
      const t = data.data.transcript;
      setMessage(`You: ${t}`);
      setConversationHistory(prev => [...prev.slice(-10), { role: 'user', content: t }]);
    } 
    else if (data.event === "actions") {
      const actions = data.data.ui_actions || [];
      actions.forEach(act => {
        const params = act.params || {};
        if (act.action === "NAVIGATE_TO") onNavigate(params.page || 'home');
        else if (act.action === "ADD_TO_CART" && params.product_id) {
          const product = products.find(p => p.id === params.product_id);
          if (product) onAddToCart(product, params.quantity || 1);
        } 
        else if (act.action === "UPDATE_CART_QUANTITY" && params.product_id) onUpdateCartQuantity(params.product_id, params.quantity);
        else if (act.action === "REMOVE_FROM_CART" && params.product_id) onRemoveFromCart(params.product_id);
        else if (act.action === "CLEAR_CART") onClearCart();
        else if (act.action === "FILTER_PRODUCTS" && params.category) onFilterCategory(params.category);
        else if (act.action === "SHOW_PRODUCT_DETAIL" && params.product_id) onSelectProductById(params.product_id);
        else if (act.action === "SHOW_PRODUCTS") {
          if (params.product_ids) onShowProducts(params.product_ids);
          else onNavigate('home');
        }
        else if (act.action === "CHECKOUT") {
          fetch(`${API_BASE}/v1/cart/checkout`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ address: params.address, payment_method: params.payment_method })
          })
          .then(res => { if (!res.ok) throw new Error(); return res.blob(); })
          .then(blob => {
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a'); a.style.display = 'none'; a.href = url; a.download = 'Invoice.pdf';
            document.body.appendChild(a); a.click(); window.URL.revokeObjectURL(url);
            onClearCart();
          }).catch(console.error);
        }
      });
    } 
    else if (data.event === "audio") {
      const responseText = data.data.response_text || "Done.";
      setMessage(responseText.length > 80 ? responseText.substring(0, 80) + '...' : responseText);
      setConversationHistory(prev => [...prev.slice(-10), { role: 'assistant', content: responseText }]);
      
      const audioB64 = data.data.audio_b64;
      if (audioB64) {
        if (audioObj.current) audioObj.current.pause();
        audioObj.current = new Audio("data:audio/mp3;base64," + audioB64);
        audioObj.current.play();
      }
      setTimeout(() => setState('idle'), 3000);
    } 
    else if (data.event === "error") {
      setMessage(data.data.error || "Error processing voice.");
      setState('idle');
    }
  };

  const startRecording = async () => {
    if (state === 'processing') return;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaRecorder.current = new MediaRecorder(stream);
      audioChunks.current = [];

      mediaRecorder.current.ondataavailable = e => {
        if (e.data.size > 0) audioChunks.current.push(e.data);
      };

      mediaRecorder.current.onstop = () => {
        processAudioStream();
        stream.getTracks().forEach(t => t.stop());
      };

      mediaRecorder.current.start();
      setState('listening');
      setMessage('Listening...');
      if (audioObj.current) audioObj.current.pause();
    } catch (err) {
      setMessage("Mic access denied");
    }
  };

  const stopRecording = () => {
    if (mediaRecorder.current && mediaRecorder.current.state === "recording") {
      mediaRecorder.current.stop();
    }
  };

  const processAudioStream = () => {
    setState('processing');
    setMessage('AI thinking...');
    
    const audioBlob = new Blob(audioChunks.current, { type: 'audio/webm' });
    const reader = new FileReader();
    reader.readAsDataURL(audioBlob);
    reader.onloadend = () => {
      const base64Audio = reader.result.split(',')[1];
      if (ws.current && ws.current.readyState === WebSocket.OPEN) {
        ws.current.send(JSON.stringify({
          audio_b64: base64Audio,
          conversation_history: conversationHistory,
          skip_tts: false
        }));
      }
    };
  };

  return (
    <div className="voice-orb-wrapper">
      <div className={`voice-tooltip ${state !== 'idle' || message ? 'visible' : ''}`}>
        {state === 'processing' && (
           <div className="visualizer" style={{marginBottom: '0.5rem'}}>
             <div className="visualizer-bar"></div><div className="visualizer-bar"></div>
             <div className="visualizer-bar"></div><div className="visualizer-bar"></div><div className="visualizer-bar"></div>
           </div>
        )}
        {message || "Hold to speak"}
      </div>
      <button 
        className={`voice-orb ${state === 'listening' ? 'listening' : state === 'processing' ? 'processing' : ''}`}
        onMouseDown={startRecording} onMouseUp={stopRecording} onMouseLeave={stopRecording}
      >
        <Mic size={28} />
      </button>
    </div>
  );
}

const CATEGORIES = ["All", "Beauty", "Fragrances", "Furniture", "Groceries"];

export default function App() {
  const [view, setView] = useState('home'); 
  const [selectedCategory, setSelectedCategory] = useState('All');
  const [selectedProduct, setSelectedProduct] = useState(null);
  const [products, setProducts] = useState([]);
  const [cartItems, setCartItems] = useState([]);
  const [searchResultsIds, setSearchResultsIds] = useState(null);

  useEffect(() => {
    if (selectedCategory === "Search Results") return;
    let url = `${API_BASE}/v1/products`;
    if (selectedCategory && selectedCategory !== "All") {
      url += `?category=${encodeURIComponent(selectedCategory)}`;
    }
    fetch(url).then(res => res.json()).then(setProducts).catch(console.error);
  }, [selectedCategory]);

  useEffect(() => { loadCart(); }, []);

  const loadCart = () => fetch(`${API_BASE}/v1/cart`).then(res => res.json()).then(setCartItems);
  const addToCart = (p, qty = 1) => fetch(`${API_BASE}/v1/cart/add`, { method: 'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({product_id: p.id, quantity: qty})}).then(loadCart);
  const updateCart = (pid, qty) => fetch(`${API_BASE}/v1/cart/update`, { method: 'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({product_id: pid, quantity: qty})}).then(loadCart);
  const removeCart = (cid) => fetch(`${API_BASE}/v1/cart/${cid}`, { method: 'DELETE' }).then(loadCart);
  const clearCart = () => fetch(`${API_BASE}/v1/cart`, { method: 'DELETE' }).then(loadCart);

  const handleNavigate = (target) => {
    let clean = (target || '').toLowerCase().replace('category/', '').trim();
    if (clean === 'home' || clean === 'cart') { setView(clean); return; }
    setSelectedCategory(CATEGORIES.find(c => c.toLowerCase().includes(clean)) || 'All');
    setView('home');
  };

  const handleShowProducts = (ids) => {
    setSearchResultsIds(ids); setSelectedCategory('Search Results'); setView('home');
    fetch(`${API_BASE}/v1/products/by-ids?ids=${ids.join(',')}`).then(res => res.json())
      .then(data => setProducts(prev => {
        const newP = [...prev];
        data.forEach(d => { if(!newP.find(p=>p.id===d.id)) newP.push(d); });
        return newP;
      }));
  };

  const handleTextSearch = (text) => {
    // Send via standard REST API for pure text search to keep it simple, or we could use WS
    const ws = new WebSocket(`${WS_BASE}/ws/chat`);
    ws.onopen = () => ws.send(JSON.stringify({ text, skip_tts: true }));
    ws.onmessage = (e) => {
      const data = JSON.parse(e.data);
      if (data.event === "actions") {
         const act = data.data.ui_actions?.[0];
         if (act && act.action === "SHOW_PRODUCTS") handleShowProducts(act.params.product_ids);
         ws.close();
      }
    };
  };

  return (
    <div>
      <Navbar cartCount={cartItems.length} setView={handleNavigate} onSearch={handleTextSearch} />
      
      {view === 'home' && (
        <div style={{padding: '2rem 2rem 0', display: 'flex', gap: '1rem'}}>
          {CATEGORIES.map(cat => (
            <button key={cat} onClick={() => setSelectedCategory(cat)} className={`btn-primary ${selectedCategory !== cat ? 'glass' : ''}`} style={selectedCategory !== cat ? {background: 'transparent', color: 'var(--text-secondary)'} : {}}>
              {cat}
            </button>
          ))}
        </div>
      )}

      {view === 'home' && <ProductGrid products={products} selectedCategory={selectedCategory} searchResultsIds={searchResultsIds} onSelectProduct={(p) => {setSelectedProduct(p); setView('detail');}} addToCart={addToCart} />}
      
      {view === 'detail' && selectedProduct && (
        <div style={{padding: '4rem 2rem', maxWidth: '1000px', margin: '0 auto'}}>
          <button className="glass" style={{padding: '0.5rem 1rem', borderRadius: '8px', cursor: 'pointer', border: 'none', color: 'white', marginBottom: '2rem'}} onClick={() => setView('home')}><ArrowLeft size={20} /></button>
          <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '4rem'}}>
            <img src={parseImage(selectedProduct.image_url) || "https://placehold.co/600"} style={{width: '100%', borderRadius: '16px'}} alt=""/>
            <div>
              <h1 style={{fontSize: '3rem', marginBottom: '1rem'}}>{selectedProduct.name}</h1>
              <p style={{fontSize: '1.5rem', color: 'var(--accent)', marginBottom: '2rem'}}>₹{selectedProduct.price.toFixed(2)}</p>
              <p style={{fontSize: '1.1rem', color: 'var(--text-secondary)', lineHeight: '1.6', marginBottom: '2rem'}}>{selectedProduct.description}</p>
              <button className="btn-primary" onClick={() => addToCart(selectedProduct)}>Add to Cart</button>
            </div>
          </div>
        </div>
      )}

      {view === 'cart' && (
        <div style={{padding: '4rem 2rem', maxWidth: '800px', margin: '0 auto'}}>
          <h1 style={{marginBottom: '2rem'}}>Shopping Cart</h1>
          {cartItems.map(item => (
            <div key={item.cart_id} className="glass" style={{padding: '1rem', display: 'flex', gap: '2rem', marginBottom: '1rem', borderRadius: '12px'}}>
              <div style={{flex: 1}}>
                <h3 style={{fontSize: '1.2rem', marginBottom: '0.5rem'}}>{item.name}</h3>
                <p>Qty: {item.quantity} | ₹{(item.price * item.quantity).toFixed(2)}</p>
              </div>
              <button style={{background: 'none', border: 'none', color: 'var(--danger)', cursor: 'pointer'}} onClick={() => removeCart(item.cart_id)}>Remove</button>
            </div>
          ))}
          {cartItems.length > 0 && <button className="btn-primary" style={{marginTop: '2rem'}} onClick={() => handleNavigate('checkout')}>Proceed to Checkout</button>}
        </div>
      )}
      
      <VoiceOrb 
        onNavigate={handleNavigate} onAddToCart={addToCart} onUpdateCartQuantity={updateCart}
        onRemoveFromCart={(pid) => { const i = cartItems.find(x=>x.id===pid); if(i) removeCart(i.cart_id); }}
        onClearCart={clearCart} onFilterCategory={(c) => {setSelectedCategory(c); setView('home');}}
        onSelectProductById={(id) => {const p = products.find(x=>x.id===id); if(p) {setSelectedProduct(p); setView('detail');}}}
        onShowProducts={handleShowProducts} products={products}
      />
    </div>
  );
}
