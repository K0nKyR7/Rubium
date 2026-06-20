// js/auth.js

const AUTH = {
    async getUser() {
        const { data: { user }, error } = await supabase.auth.getUser();
        if (error || !user) return null;
        return user;
    },

    async getProfile() {
        const user = await this.getUser();
        if (!user) return null;
        
        const { data, error } = await supabase
            .from('users')
            .select('*')
            .eq('id', user.id)
            .single();
        
        if (error || !data) return null;
        return data;
    },

    async logout() {
        await supabase.auth.signOut();
        window.location.href = 'index.html';
    },

    async requireAuth() {
        const user = await this.getUser();
        if (!user) {
            window.location.href = 'login.html';
            return null;
        }
        return user;
    },

    async requireAdmin() {
        const profile = await this.getProfile();
        if (!profile || profile.role !== 'admin') {
            window.location.href = 'index.html';
            return null;
        }
        return profile;
    }
};