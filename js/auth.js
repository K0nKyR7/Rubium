const AUTH = {
    async getUser() {
        const { data } = await supabase.auth.getSession();
        if (!data || !data.session) return null;
        return data.session.user;
    },

    async getProfile() {
        const user = await this.getUser();
        if (!user) return null;
        const { data } = await supabase.from('users').select('*').eq('id', user.id).single();
        return data || null;
    },

    async logout() {
        await supabase.auth.signOut();
        localStorage.clear();
        window.location.href = 'index.html';
    },

    async requireAuth() {
        const user = await this.getUser();
        if (!user) {
            window.location.href = 'login.html';
            return null;
        }
        return user;
    }
};