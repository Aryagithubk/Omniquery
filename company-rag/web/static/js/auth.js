const authForm = document.getElementById('auth-form');
const emailInput = document.getElementById('email');
const passwordInput = document.getElementById('password');
const authSubmitBtn = document.getElementById('auth-submit');
const authError = document.getElementById('auth-error');
const tabLogin = document.getElementById('tab-login');
const tabRegister = document.getElementById('tab-register');

// Form dynamic fields
const rFirstName = document.getElementById('firstName');
const rLastName = document.getElementById('lastName');
const rDepartment = document.getElementById('department');
const rJobTitle = document.getElementById('jobTitle');
const rSalary = document.getElementById('salary');
const rHireDate = document.getElementById('hireDate');

let isLoginMode = true;

// Auth Tabs 
tabLogin.addEventListener('click', () => {
    isLoginMode = true;
    tabLogin.classList.add('active');
    tabRegister.classList.remove('active');
    document.body.classList.remove('register-mode');
    authSubmitBtn.textContent = 'Login';
    authError.style.display = 'none';
});

tabRegister.addEventListener('click', () => {
    isLoginMode = false;
    tabRegister.classList.add('active');
    tabLogin.classList.remove('active');
    document.body.classList.add('register-mode');
    authSubmitBtn.textContent = 'Register';
    authError.style.display = 'none';
});

// Submit
authForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const email = emailInput.value.trim();
    const password = passwordInput.value;
    
    if (!email || !password) return;

    let payload = {};
    const endpoint = isLoginMode ? '/api/v1/auth/login' : '/api/v1/auth/register';

    if (isLoginMode) {
        payload = { email, password };
    } else {
        payload = {
            first_name: rFirstName.value.trim() || 'New',
            last_name: rLastName.value.trim() || 'Employee',
            email: email,
            password: password,
            department_id: parseInt(rDepartment.value) || 1,
            job_title: rJobTitle.value.trim() || 'Staff',
            salary: parseFloat(rSalary.value) || 60000,
            hire_date: rHireDate.value || new Date().toISOString().split('T')[0]
        };
    }
    
    authSubmitBtn.disabled = true;
    authError.style.display = 'none';
    
    try {
        const res = await fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        
        const data = await res.json();
        
        if (!res.ok) {
            throw new Error(data.detail || 'Authentication failed');
        }
        
        localStorage.setItem('token', data.access_token);
        localStorage.setItem('role', data.role);
        
        // Redirect to AI Chat page
        window.location.href = '/';
        
    } catch (err) {
        authError.textContent = err.message;
        authError.style.display = 'block';
    } finally {
        authSubmitBtn.disabled = false;
    }
});
