import { PublicClientApplication, type AuthenticationResult } from '@azure/msal-browser';
import type { MSALConfig } from './AppConfig.js';

class MSAL {
    msalConfig: MSALConfig;
    publicClientApplication: PublicClientApplication;
    constructor(config: MSALConfig) {
        this.msalConfig = config;
        this.publicClientApplication = new PublicClientApplication(this.msalConfig);
    }


    public async authenticate(): Promise<AuthenticationResult> {
        const accessTokenRequest = {
            scopes: [`api://${this.msalConfig.auth.clientId}/${this.msalConfig.auth.scope}`]
        };
        return new Promise((resolve, reject) => {
            this.publicClientApplication.initialize().then(() => {
                this.publicClientApplication.handleRedirectPromise()
                    .then(redirectResponse => {
                        // Acquire token silent success
                        if (redirectResponse != null) {
                            this.publicClientApplication.setActiveAccount(redirectResponse.account);
                            resolve(redirectResponse);
                        }
                        else {
                            const account = this.publicClientApplication.getActiveAccount();
                            const silentRequest = {
                                ...accessTokenRequest,
                                account: account == null ? undefined : account
                            };
                            this.publicClientApplication.acquireTokenSilent(silentRequest)
                                .then(accessTokenResponse => {
                                    resolve(accessTokenResponse);
                                })
                                .catch(error => {
                                    this.publicClientApplication.acquireTokenRedirect(accessTokenRequest);
                                    reject(error);
                                });
                        }
                    })
            }).catch(err => reject(err));
        });
    }
}

export { MSAL, type AuthenticationResult };
