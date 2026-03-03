import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { FiPenTool, FiBookmark, FiUser, FiLogOut, FiLogIn, FiMenu, FiX } from 'react-icons/fi';
import { useState } from 'react';

export default function Navbar() {
    const { user, logout } = useAuth();
    const navigate = useNavigate();
    const [menuOpen, setMenuOpen] = useState(false);

    const handleLogout = () => {
        logout();
        navigate('/login');
        setMenuOpen(false);
    };

    return (
        <nav className="navbar">
            <div className="navbar-container">
                <Link to="/" className="navbar-brand" onClick={() => setMenuOpen(false)}>
                    <FiPenTool className="brand-icon" />
                    <span>Blogger</span>
                </Link>

                <button className="menu-toggle" onClick={() => setMenuOpen(!menuOpen)}>
                    {menuOpen ? <FiX /> : <FiMenu />}
                </button>

                <div className={`navbar-links ${menuOpen ? 'open' : ''}`}>
                    <Link to="/" className="nav-link" onClick={() => setMenuOpen(false)}>Home</Link>

                    {user ? (
                        <>
                            <Link to="/create" className="nav-link" onClick={() => setMenuOpen(false)}>
                                Write
                            </Link>
                            <Link to="/bookmarks" className="nav-link" onClick={() => setMenuOpen(false)}>
                                <FiBookmark /> Bookmarks
                            </Link>
                            <Link to="/profile" className="nav-link profile-link" onClick={() => setMenuOpen(false)}>
                                {user.profilePicUrl ? (
                                    <img src={user.profilePicUrl} alt="" className="nav-avatar" />
                                ) : (
                                    <FiUser />
                                )}
                                {user.name}
                            </Link>
                            <button onClick={handleLogout} className="nav-btn logout-btn">
                                <FiLogOut /> Logout
                            </button>
                        </>
                    ) : (
                        <>
                            <Link to="/login" className="nav-link" onClick={() => setMenuOpen(false)}>
                                <FiLogIn /> Login
                            </Link>
                            <Link to="/register" className="nav-btn register-btn" onClick={() => setMenuOpen(false)}>
                                Get Started
                            </Link>
                        </>
                    )}
                </div>
            </div>
        </nav>
    );
}
